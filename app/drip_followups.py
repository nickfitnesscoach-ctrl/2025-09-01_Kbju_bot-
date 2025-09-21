"""Фоновая рассылка DRIP-сообщений по неактивности."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import func, not_, or_, select

from app.database.models import User, async_session
from app.database.requests import update_drip_stage
from app.texts import get_media_id, get_text
from config import (
    DRIP_24H_MIN,
    DRIP_48H_MIN,
    DRIP_72H_MIN,
    DRIP_CHECK_INTERVAL_SEC,
    ENABLE_DRIP_FOLLOWUPS,
)

logger = logging.getLogger(__name__)

_STAGE_LABELS = {1: "24h", 2: "48h", 3: "72h"}
_STAGE_THRESHOLDS = {1: DRIP_24H_MIN, 2: DRIP_48H_MIN, 3: DRIP_72H_MIN}


@dataclass(slots=True)
class DripCandidate:
    tg_id: int
    funnel_status: str | None
    gender: str | None
    drip_stage: int
    last_activity_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None


def _normalize_status(status: str | None) -> str:
    return (status or "").strip().lower()


def _to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _format_dt(value: datetime | None) -> str:
    normalized = _to_utc_naive(value)
    if normalized is None:
        return "none"
    try:
        return normalized.replace(microsecond=0).isoformat() + "Z"
    except Exception:  # noqa: BLE001 - best effort for logging
        return str(normalized)


def _resolve_activity(candidate: DripCandidate) -> tuple[datetime | None, str | None]:
    last_activity = _to_utc_naive(candidate.last_activity_at)
    updated_at = _to_utc_naive(candidate.updated_at)
    created_at = _to_utc_naive(candidate.created_at)

    if last_activity is not None:
        return last_activity, "last_activity_at"
    if updated_at is not None:
        return updated_at, "updated_at"
    if created_at is not None:
        return created_at, "created_at"
    return None, None


def _threshold_for_stage(stage: int) -> int:
    return _STAGE_THRESHOLDS.get(stage, 0)


def _next_stage(current_stage: int) -> int | None:
    if current_stage is None:
        current_stage = 0
    if current_stage >= 3:
        return None
    target_stage = current_stage + 1
    if target_stage not in _STAGE_THRESHOLDS:
        return None
    return target_stage


def _minutes_since(reference: datetime | None) -> float | None:
    if reference is None:
        return None
    delta = datetime.utcnow() - reference
    return delta.total_seconds() / 60.0


def _stage_text_candidates(stage: int, gender: str | None) -> Iterable[str]:
    base_key = {1: "drip.case_24h", 2: "drip.case_48h", 3: "drip.case_72h"}.get(stage)
    if not base_key:
        return []

    normalized_gender = (gender or "").strip().lower()
    candidates: list[str] = []

    if stage in (1, 2):
        if normalized_gender in {"male", "female"}:
            candidates.append(f"{base_key}.{normalized_gender}.text")
        candidates.extend(
            key
            for key in (
                f"{base_key}.any.text",
                f"{base_key}.male.text",
                f"{base_key}.female.text",
            )
            if key not in candidates
        )
    else:
        candidates.append(f"{base_key}.any.text")
        candidates.append(f"{base_key}.text")

    return candidates


def _choose_stage_text(stage: int, gender: str | None) -> tuple[str | None, str | None]:
    for key in _stage_text_candidates(stage, gender):
        text = get_text(key)
        if text.startswith("[Текст не найден"):
            continue
        return text, key
    return None, None


async def _send_stage(bot: Bot, candidate: DripCandidate, stage: int) -> tuple[bool, str | None, str | None]:
    text, key = _choose_stage_text(stage, candidate.gender)
    if not text:
        return False, key, "template-not-found"

    base_key = key.rsplit(".", 1)[0] if key else None
    photo_id = get_media_id(f"{base_key}.photo_file_id") if base_key else None
    video_id = get_media_id(f"{base_key}.video_file_id") if base_key else None

    try:
        if photo_id:
            await bot.send_photo(chat_id=candidate.tg_id, photo=photo_id)
    except asyncio.CancelledError:  # pragma: no cover - cooperates with shutdown
        raise
    except Exception as exc:  # noqa: BLE001 - attachments are optional, continue with text
        logger.warning(
            "DRIP photo send failed | user=%s | stage=%s | error=%s",
            candidate.tg_id,
            stage,
            exc,
        )

    try:
        if video_id:
            await bot.send_video(chat_id=candidate.tg_id, video=video_id)
    except asyncio.CancelledError:  # pragma: no cover - cooperates with shutdown
        raise
    except Exception as exc:  # noqa: BLE001 - attachments are optional, continue with text
        logger.warning(
            "DRIP video send failed | user=%s | stage=%s | error=%s",
            candidate.tg_id,
            stage,
            exc,
        )

    try:
        await bot.send_message(chat_id=candidate.tg_id, text=text, parse_mode="HTML")
    except asyncio.CancelledError:  # pragma: no cover - cooperates with shutdown
        raise
    except Exception as exc:  # noqa: BLE001 - log failure and retry later
        logger.warning(
            "DRIP send failed | user=%s | stage=%s | label=%s | error=%s",
            candidate.tg_id,
            stage,
            _STAGE_LABELS.get(stage, stage),
            exc,
        )
        return False, key, str(exc)

    return True, key, None


def _log_verdict(candidate: DripCandidate, message: str) -> None:
    logger.info(
        "DRIP verdict | user=%s | %s",
        candidate.tg_id,
        message,
    )


async def _process_candidate(bot: Bot, candidate: DripCandidate) -> None:
    status = _normalize_status(candidate.funnel_status)

    if status.startswith("hotlead"):
        _log_verdict(candidate, f"skip (hotlead) status={status}")
        return

    eligible = status in {"new", "calculated"} or status.startswith("coldlead")
    if not eligible:
        _log_verdict(candidate, f"skip (status-not-eligible) status={status or 'unknown'}")
        return

    current_stage = max(0, int(candidate.drip_stage or 0))
    next_stage = _next_stage(current_stage)
    if next_stage is None:
        _log_verdict(candidate, "done (already stage=3)")
        return

    reference, source = _resolve_activity(candidate)
    if reference is None:
        _log_verdict(
            candidate,
            (
                "skip (no-activity-reference)"
                + (f" status={status}" if status else "")
                + f" last_activity={_format_dt(candidate.last_activity_at)}"
                + f" updated={_format_dt(candidate.updated_at)}"
                + f" created={_format_dt(candidate.created_at)}"
            ),
        )
        return

    minutes = _minutes_since(reference)
    if minutes is None:
        _log_verdict(
            candidate,
            (
                "skip (no-activity-reference)"
                + (f" status={status}" if status else "")
                + f" last_activity={_format_dt(candidate.last_activity_at)}"
                + f" updated={_format_dt(candidate.updated_at)}"
                + f" created={_format_dt(candidate.created_at)}"
            ),
        )
        return

    minutes = max(0.0, minutes)
    threshold = _threshold_for_stage(next_stage)
    if minutes < threshold:
        _log_verdict(
            candidate,
            f"skip (no-threshold) minutes={minutes:.1f} needed={threshold} source={source} status={status}",
        )
        return

    sent, text_key, error = await _send_stage(bot, candidate, next_stage)
    if not sent:
        details = error or "unknown-error"
        _log_verdict(candidate, f"send fail (stage {next_stage}): {details}")
        return

    updated = await update_drip_stage(
        candidate.tg_id,
        from_stage=current_stage,
        to_stage=next_stage,
    )
    if updated:
        candidate.drip_stage = next_stage
    else:
        logger.debug(
            "DRIP stage advance skipped | user=%s | from=%s | target=%s",
            candidate.tg_id,
            current_stage,
            next_stage,
        )

    suffix_parts = [
        f"send ok (stage {next_stage})",
        f"minutes={minutes:.1f}",
        f"source={source}",
    ]
    if text_key:
        suffix_parts.append(f"text={text_key}")
    if status:
        suffix_parts.append(f"status={status}")
    _log_verdict(candidate, " ".join(suffix_parts))


async def _load_candidates() -> tuple[Sequence[DripCandidate], str]:
    status_expr = func.lower(func.coalesce(User.funnel_status, ""))
    query = (
        select(User)
        .where(
            or_(
                status_expr == "new",
                status_expr == "calculated",
                status_expr.like("coldlead%"),
            ),
            not_(status_expr.like("hotlead%")),
        )
        .order_by(User.id)
    )

    async with async_session() as session:
        result = await session.scalars(query)
        users = result.all()

    snapshots: list[DripCandidate] = []
    for user in users:
        snapshots.append(
            DripCandidate(
                tg_id=user.tg_id,
                funnel_status=user.funnel_status,
                gender=getattr(user, "gender", None),
                drip_stage=max(0, int(getattr(user, "drip_stage", 0) or 0)),
                last_activity_at=getattr(user, "last_activity_at", None),
                updated_at=getattr(user, "updated_at", None),
                created_at=getattr(user, "created_at", None),
            )
        )

    return snapshots, str(query)


class DripFollowupService:
    """Периодический воркер для DRIP-рассылок."""

    _task: asyncio.Task | None = None
    _stop_event: asyncio.Event | None = None
    _bot: Bot | None = None

    @classmethod
    def start(cls, bot: Bot) -> None:
        logger.info(
            "DRIP worker bootstrap | enabled=%s | pid=%s | already_running=%s | interval_sec=%s | thresholds_min=(24h=%s, 48h=%s, 72h=%s)",
            ENABLE_DRIP_FOLLOWUPS,
            os.getpid(),
            cls.is_running(),
            DRIP_CHECK_INTERVAL_SEC,
            DRIP_24H_MIN,
            DRIP_48H_MIN,
            DRIP_72H_MIN,
        )

        if not ENABLE_DRIP_FOLLOWUPS:
            logger.info("DRIP follow-ups disabled; background worker not started")
            return

        if cls._task and not cls._task.done():
            logger.info("DRIP follow-up worker already running; skipping start")
            return

        cls._bot = bot
        cls._stop_event = asyncio.Event()
        cls._task = asyncio.create_task(cls._runner())
        logger.info("DRIP worker started (interval=%ss)", DRIP_CHECK_INTERVAL_SEC)

    @classmethod
    def is_running(cls) -> bool:
        return bool(cls._task and not cls._task.done())

    @classmethod
    async def stop(cls) -> None:
        if not cls._task:
            return

        if cls._stop_event:
            cls._stop_event.set()

        task = cls._task
        cls._task = None
        try:
            await task
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            pass
        finally:
            cls._stop_event = None
            cls._bot = None
            logger.info("DRIP worker stopped")

    @classmethod
    async def _runner(cls) -> None:
        assert cls._stop_event is not None
        iteration = 0

        try:
            while True:
                if cls._stop_event.is_set():
                    break

                bot = cls._bot
                if not bot:
                    logger.debug("DRIP worker idle: bot instance missing")
                else:
                    iteration += 1
                    started_at = datetime.utcnow()
                    logger.info(
                        "DRIP scan start | iteration=%s | utc=%s",
                        iteration,
                        _format_dt(started_at),
                    )

                    try:
                        candidates, query_text = await _load_candidates()
                        logger.info("DRIP selection query | %s", query_text)
                        logger.info(
                            "DRIP candidates loaded | count=%s",
                            len(candidates),
                        )
                        for candidate in candidates:
                            await _process_candidate(bot, candidate)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("DRIP worker iteration failed: %s", exc)
                    else:
                        duration = datetime.utcnow() - started_at
                        logger.info(
                            "DRIP scan end | iteration=%s | duration=%.2fs",
                            iteration,
                            duration.total_seconds(),
                        )

                try:
                    await asyncio.wait_for(
                        cls._stop_event.wait(), timeout=DRIP_CHECK_INTERVAL_SEC
                    )
                    break
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            logger.debug("DRIP worker task cancelled")
            raise

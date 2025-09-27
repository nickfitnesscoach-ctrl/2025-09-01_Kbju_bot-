"""Фоновая рассылка DRIP-сообщений по неактивности."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, not_, or_, select

from app.database.models import User, async_session
from app.database.requests import update_drip_stage
from app.texts import get_button_text, get_media_id, get_optional_text, get_text
from app.utils import CAPTION_LIMIT, strip_html
from config import (
    DRIP_CHECK_INTERVAL_SEC,
    DRIP_STAGE_1_MIN,
    DRIP_STAGE_2_MIN,
    ENABLE_DRIP_FOLLOWUPS,
)

logger = logging.getLogger(__name__)

_STAGE_LABELS = {1: "1h", 2: "24h"}
_STAGE_THRESHOLDS = {1: DRIP_STAGE_1_MIN, 2: DRIP_STAGE_2_MIN}


@dataclass(slots=True)
class StageContent:
    base_key: str
    text: str
    photo_id: str | None
    video_id: str | None
    image_url: str | None
    button_text: str | None
    button_callback: str | None
    button_url: str | None


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
    target_stage = current_stage + 1
    if target_stage not in _STAGE_THRESHOLDS:
        return None
    return target_stage


def _minutes_since(reference: datetime | None) -> float | None:
    if reference is None:
        return None
    delta = datetime.utcnow() - reference
    return delta.total_seconds() / 60.0


def _stage_base_keys(stage: int, status: str | None) -> Iterable[str]:
    normalized_status = (status or "").strip().lower()
    base_keys: list[str] = []
    if normalized_status:
        base_keys.append(f"drip.{normalized_status}.stage_{stage}")
    base_keys.append(f"drip.any.stage_{stage}")
    return base_keys


def _choose_stage_content(stage: int, status: str | None) -> StageContent | None:
    for base_key in _stage_base_keys(stage, status):
        text = get_text(f"{base_key}.text")
        if text.startswith("[Текст не найден"):
            continue

        photo_id = get_media_id(f"{base_key}.photo_file_id")
        video_id = get_media_id(f"{base_key}.video_file_id")
        image_url = get_media_id(f"{base_key}.image_url")

        button_text = get_optional_text(f"{base_key}.button_text")
        button_text_key = get_optional_text(f"{base_key}.button_text_key")
        if not button_text and button_text_key:
            button_text = get_button_text(button_text_key)
        button_callback = get_optional_text(f"{base_key}.button_callback")
        button_url = get_optional_text(f"{base_key}.button_url")

        return StageContent(
            base_key=base_key,
            text=text,
            photo_id=photo_id,
            video_id=video_id,
            image_url=image_url,
            button_text=button_text,
            button_callback=button_callback,
            button_url=button_url,
        )

    return None


async def _send_stage(
    bot: Bot,
    candidate: DripCandidate,
    stage: int,
    content: StageContent,
) -> tuple[bool, str | None, str | None]:
    reply_markup: InlineKeyboardMarkup | None = None
    button_text = content.button_text
    if button_text:
        if content.button_url:
            button = InlineKeyboardButton(text=button_text, url=content.button_url)
        elif content.button_callback:
            button = InlineKeyboardButton(
                text=button_text,
                callback_data=content.button_callback,
            )
        else:
            button = None
        if button:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[button]])

    if content.photo_id or content.image_url:
        caption_length = len(strip_html(content.text))
        if caption_length > CAPTION_LIMIT:
            logger.warning(
                "DRIP caption too long | user=%s | stage=%s | length=%s | limit=%s",
                candidate.tg_id,
                stage,
                caption_length,
                CAPTION_LIMIT,
            )
        else:
            media_id = content.photo_id or content.image_url
            try:
                await bot.send_photo(
                    chat_id=candidate.tg_id,
                    photo=media_id,
                    caption=content.text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except Exception as exc:  # noqa: BLE001 - fall back to text
                logger.warning(
                    "DRIP photo with caption send failed | user=%s | stage=%s | error=%s",
                    candidate.tg_id,
                    stage,
                    exc,
                )
            else:
                return True, content.base_key + ".text", None

    if content.photo_id and not reply_markup:
        try:
            await bot.send_photo(chat_id=candidate.tg_id, photo=content.photo_id)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DRIP photo send failed | user=%s | stage=%s | error=%s",
                candidate.tg_id,
                stage,
                exc,
            )

    if content.video_id:
        try:
            await bot.send_video(chat_id=candidate.tg_id, video=content.video_id)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DRIP video send failed | user=%s | stage=%s | error=%s",
                candidate.tg_id,
                stage,
                exc,
            )

    try:
        await bot.send_message(
            chat_id=candidate.tg_id,
            text=content.text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except asyncio.CancelledError:  # pragma: no cover
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DRIP send failed | user=%s | stage=%s | label=%s | error=%s",
            candidate.tg_id,
            stage,
            _STAGE_LABELS.get(stage, stage),
            exc,
        )
        return False, content.base_key + ".text", str(exc)

    return True, content.base_key + ".text", None


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

    eligible = status in {"new", "calculated"}
    if not eligible:
        _log_verdict(candidate, f"skip (status-not-eligible) status={status or 'unknown'}")
        return

    current_stage = max(0, int(candidate.drip_stage or 0))
    next_stage = _next_stage(current_stage)
    if next_stage is None:
        _log_verdict(candidate, "done (already stage=1)")
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

    content = _choose_stage_content(next_stage, status)
    if not content:
        _log_verdict(candidate, f"skip (template-not-found) stage={next_stage} status={status}")
        return

    sent, text_key, error = await _send_stage(bot, candidate, next_stage, content)
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
            "DRIP worker bootstrap | enabled=%s | pid=%s | already_running=%s | interval_sec=%s | thresholds_min=(stage1=%s)",
            ENABLE_DRIP_FOLLOWUPS,
            os.getpid(),
            cls.is_running(),
            DRIP_CHECK_INTERVAL_SEC,
            DRIP_STAGE_1_MIN,
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

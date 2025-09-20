"""Фоновая рассылка догоняющих кейсов по неактивности."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple

from aiogram import Bot
from sqlalchemy import or_, select

from app.constants import FUNNEL_STATUSES
from app.database.models import User, async_session
from app.database.requests import update_drip_stage
from app.texts import get_text
from config import (
    DRIP_24H_MIN,
    DRIP_48H_MIN,
    DRIP_72H_MIN,
    DRIP_CHECK_INTERVAL_SEC,
    ENABLE_DRIP_FOLLOWUPS,
)

logger = logging.getLogger(__name__)

_STAGE_LABELS = {1: "24h", 2: "48h", 3: "72h"}

_COHORTS: Tuple[str, ...] = ("stalled", "tips")


@dataclass(slots=True)
class DripUserSnapshot:
    tg_id: int
    gender: str | None
    funnel_status: str | None
    last_activity_at: datetime | None
    activity_at: datetime | None
    activity_source: str | None
    created_at: datetime | None
    updated_at: datetime | None
    drip_stage_stalled: int
    drip_stage_tips: int
    has_started: bool


def _has_started(user: User) -> bool:
    return any(
        getattr(user, field, None)
        for field in ("gender", "age", "weight", "height", "activity", "goal")
    )


def _normalize_status(status: str | None) -> str:
    return (status or "").strip().lower()


def _is_finished_status(status: str | None) -> bool:
    normalized = _normalize_status(status)
    if not normalized:
        return False
    if normalized == FUNNEL_STATUSES["calculated"]:
        return True
    if normalized.startswith("hotlead"):
        return True
    return normalized == FUNNEL_STATUSES["coldlead"]


def _determine_next_stage(current_stage: int, elapsed_minutes: float) -> int | None:
    if current_stage < 0:
        current_stage = 0
    if current_stage == 0 and elapsed_minutes >= DRIP_24H_MIN:
        return 1
    if current_stage <= 1 and elapsed_minutes >= DRIP_48H_MIN:
        return 2
    if current_stage <= 2 and elapsed_minutes >= DRIP_72H_MIN:
        return 3
    return None


def _candidate_text_keys(stage_to_set: int, gender: str | None) -> List[str]:
    base = {
        1: "drip.case_24h",
        2: "drip.case_48h",
        3: "drip.case_72h",
    }.get(stage_to_set)
    if not base:
        return []

    gender_normalized = (gender or "").strip().lower()
    keys: list[str] = []

    if stage_to_set == 3:
        keys.append(f"{base}.any.text")
    else:
        if gender_normalized == "male":
            keys.append(f"{base}.male.text")
        elif gender_normalized == "female":
            keys.append(f"{base}.female.text")
        else:
            keys.append(f"{base}.any.text")

        for fallback in (f"{base}.any.text", f"{base}.male.text", f"{base}.female.text"):
            if fallback not in keys:
                keys.append(fallback)

    return keys


def _to_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _format_dt(value: datetime | None) -> str:
    naive_value = _to_naive(value)
    if naive_value is None:
        return "none"
    try:
        return naive_value.replace(microsecond=0).isoformat() + "Z"
    except Exception:  # noqa: BLE001 - best effort formatting
        return str(naive_value)


def _resolve_activity_timestamp(
    last_activity: datetime | None,
    updated_at: datetime | None,
    created_at: datetime | None,
) -> tuple[datetime | None, str | None]:
    last_activity = _to_naive(last_activity)
    updated_at = _to_naive(updated_at)
    created_at = _to_naive(created_at)

    if last_activity:
        return last_activity, "last_activity_at"

    fallback_candidates = [
        candidate
        for candidate in ((updated_at, "updated_at"), (created_at, "created_at"))
        if candidate[0] is not None
    ]
    if not fallback_candidates:
        return None, None

    fallback_candidates.sort(key=lambda item: item[0], reverse=True)
    chosen_dt, chosen_source = fallback_candidates[0]
    return chosen_dt, chosen_source


def _threshold_for_stage(stage: int) -> int:
    return {1: DRIP_24H_MIN, 2: DRIP_48H_MIN, 3: DRIP_72H_MIN}.get(stage, 0)


def _cohort_membership(snapshot: DripUserSnapshot, cohort: str) -> tuple[bool, str]:
    status = _normalize_status(snapshot.funnel_status)

    if cohort == "stalled":
        if not snapshot.has_started:
            return False, "not_started"
        if _is_finished_status(status):
            return False, "finished_status"
        if status == FUNNEL_STATUSES["coldlead_delayed"]:
            return False, "tips_branch"
        return True, "eligible"

    if cohort == "tips":
        if status == FUNNEL_STATUSES["coldlead_delayed"]:
            return True, "eligible"
        if _is_finished_status(status):
            return False, "finished_status"
        return False, "status_mismatch"

    return False, "unknown_cohort"


async def _load_candidates() -> tuple[list[DripUserSnapshot], str]:
    query = select(User).where(
        or_(User.drip_stage_stalled < 3, User.drip_stage_tips < 3)
    )
    async with async_session() as session:
        result = await session.scalars(query)
        users = result.all()

    snapshots: list[DripUserSnapshot] = []
    for user in users:
        last_activity = _to_naive(getattr(user, "last_activity_at", None))
        updated_at = _to_naive(getattr(user, "updated_at", None))
        created_at = _to_naive(getattr(user, "created_at", None))
        activity_at, activity_source = _resolve_activity_timestamp(
            last_activity,
            updated_at,
            created_at,
        )
        snapshots.append(
            DripUserSnapshot(
                tg_id=user.tg_id,
                gender=user.gender,
                funnel_status=user.funnel_status,
                last_activity_at=last_activity,
                activity_at=activity_at,
                activity_source=activity_source,
                created_at=created_at,
                updated_at=updated_at,
                drip_stage_stalled=int(getattr(user, "drip_stage_stalled", 0) or 0),
                drip_stage_tips=int(getattr(user, "drip_stage_tips", 0) or 0),
                has_started=_has_started(user),
            )
        )
    return snapshots, str(query)


async def _send_followup(
    bot: Bot, snapshot: DripUserSnapshot, cohort: str, stage_to_set: int
) -> bool:
    candidates = _candidate_text_keys(stage_to_set, snapshot.gender)
    text_to_send: str | None = None
    chosen_key: str | None = None

    for key in candidates:
        text = get_text(key)
        if text.startswith("[Текст не найден"):
            continue
        chosen_key = key
        text_to_send = text
        break

    if not text_to_send:
        logger.warning(
            "DRIP %s skipped for user %s (cohort=%s): no text configured",
            _STAGE_LABELS.get(stage_to_set, str(stage_to_set)),
            snapshot.tg_id,
            cohort,
        )
        return False

    if (
        chosen_key
        and chosen_key.endswith(".any.text")
        and (snapshot.gender or "").strip().lower() not in {"male", "female"}
    ):
        logger.info(
            "DRIP %s using fallback text for user %s (cohort=%s): gender unknown -> %s",
            _STAGE_LABELS.get(stage_to_set, str(stage_to_set)),
            snapshot.tg_id,
            cohort,
            chosen_key,
        )

    try:
        await bot.send_message(
            chat_id=snapshot.tg_id,
            text=text_to_send,
            parse_mode="HTML",
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DRIP %s failed for user %s (cohort=%s): %s",
            _STAGE_LABELS.get(stage_to_set, str(stage_to_set)),
            snapshot.tg_id,
            cohort,
            exc,
        )
        return False

    logger.info(
        "DRIP %s sent to user %s (cohort=%s, gender=%s, text_key=%s)",
        _STAGE_LABELS.get(stage_to_set, str(stage_to_set)),
        snapshot.tg_id,
        cohort,
        snapshot.gender or "unknown",
        chosen_key,
    )

    try:
        updated = await update_drip_stage(
            snapshot.tg_id, cohort=cohort, stage=stage_to_set
        )
        if not updated:
            logger.info(
                "DRIP stage already set for user %s (cohort=%s): stage=%s",
                snapshot.tg_id,
                cohort,
                stage_to_set,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DRIP stage update failed for user %s (cohort=%s): %s",
            snapshot.tg_id,
            cohort,
            exc,
        )

    return True


async def _ensure_stage_guard(
    snapshot: DripUserSnapshot, cohort: str, stage_to_set: int
) -> tuple[bool, str, int | None]:
    column_name = "drip_stage_stalled" if cohort == "stalled" else "drip_stage_tips"

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == snapshot.tg_id))

    if not user:
        return False, "user_missing", None

    current_stage_db = int(getattr(user, column_name, 0) or 0)
    snapshot_stage = int(getattr(snapshot, column_name, 0) or 0)

    if current_stage_db > snapshot_stage:
        logger.debug(
            "DRIP %s stage drift detected for user %s (cohort=%s): snapshot=%s db=%s",
            _STAGE_LABELS.get(stage_to_set, str(stage_to_set)),
            snapshot.tg_id,
            cohort,
            snapshot_stage,
            current_stage_db,
        )
        setattr(snapshot, column_name, current_stage_db)

    if current_stage_db >= stage_to_set:
        return False, f"stage_already_{current_stage_db}", current_stage_db

    return True, "ok", current_stage_db


async def _process_snapshot(
    bot: Bot, snapshot: DripUserSnapshot
) -> list[tuple[str, int, bool]]:
    decisions: list[tuple[str, int, bool]] = []

    if snapshot.tg_id is None:
        return decisions

    activity_at = snapshot.activity_at
    if activity_at is None:
        logger.info(
            "DRIP candidate skipped | user=%s | reason=no_activity_timestamp | "
            "last_activity=%s | updated_at=%s | created_at=%s",
            snapshot.tg_id,
            _format_dt(snapshot.last_activity_at),
            _format_dt(snapshot.updated_at),
            _format_dt(snapshot.created_at),
        )
        return decisions

    now_utc = datetime.utcnow()
    elapsed_seconds = (now_utc - activity_at).total_seconds()
    if elapsed_seconds < 0:
        logger.info(
            "DRIP candidate skipped | user=%s | reason=activity_in_future | "
            "activity_at=%s | now=%s",
            snapshot.tg_id,
            _format_dt(activity_at),
            _format_dt(now_utc),
        )
        return decisions

    elapsed_minutes = elapsed_seconds / 60.0
    logger.info(
        "DRIP candidate | user=%s | status=%s | gender=%s | reference=%s (%s) | "
        "minutes_since=%.1f | stages(stalled=%s, tips=%s)",
        snapshot.tg_id,
        _normalize_status(snapshot.funnel_status) or "unknown",
        snapshot.gender or "unknown",
        _format_dt(activity_at),
        snapshot.activity_source or "unknown",
        elapsed_minutes,
        snapshot.drip_stage_stalled,
        snapshot.drip_stage_tips,
    )

    for cohort in _COHORTS:
        eligible, eligibility_reason = _cohort_membership(snapshot, cohort)
        stage_attr = "drip_stage_stalled" if cohort == "stalled" else "drip_stage_tips"
        current_stage = int(getattr(snapshot, stage_attr, 0) or 0)

        if not eligible:
            logger.info(
                "DRIP evaluation | user=%s | cohort=%s | decision=skip | reason=%s | "
                "stage=%s | minutes_since=%.1f",
                snapshot.tg_id,
                cohort,
                eligibility_reason,
                current_stage,
                elapsed_minutes,
            )
            continue

        if current_stage >= 3:
            logger.info(
                "DRIP evaluation | user=%s | cohort=%s | decision=skip | "
                "reason=completed_all_stages | stage=%s",
                snapshot.tg_id,
                cohort,
                current_stage,
            )
            continue

        stage_to_set = _determine_next_stage(current_stage, elapsed_minutes)
        if not stage_to_set or stage_to_set <= current_stage:
            logger.info(
                "DRIP evaluation | user=%s | cohort=%s | decision=skip | "
                "reason=below_threshold(%.1f<%s) | stage=%s",
                snapshot.tg_id,
                cohort,
                elapsed_minutes,
                _threshold_for_stage(current_stage + 1),
                current_stage,
            )
            continue

        decisions.append((cohort, stage_to_set, False))
        guard_ok, guard_reason, guard_stage = await _ensure_stage_guard(
            snapshot, cohort, stage_to_set
        )
        if not guard_ok:
            logger.info(
                "DRIP evaluation | user=%s | cohort=%s | stage_target=%s | "
                "decision=skip | reason=%s | db_stage=%s",
                snapshot.tg_id,
                cohort,
                stage_to_set,
                guard_reason,
                guard_stage,
            )
            continue

        sent = await _send_followup(bot, snapshot, cohort, stage_to_set)
        decisions[-1] = (cohort, stage_to_set, sent)
        if sent:
            setattr(snapshot, stage_attr, stage_to_set)
        else:
            logger.info(
                "DRIP evaluation | user=%s | cohort=%s | stage_target=%s | "
                "decision=skip | reason=send_failed",
                snapshot.tg_id,
                cohort,
                stage_to_set,
            )

    return decisions


class DripFollowupService:
    """Периодический сканер пользователей для отправки кейсов."""

    _task: asyncio.Task | None = None
    _stop_event: asyncio.Event | None = None
    _bot: Bot | None = None

    @classmethod
    def start(cls, bot: Bot) -> None:
        logger.info(
            "DRIP worker bootstrap | enabled=%s | pid=%s | already_running=%s | "
            "interval_sec=%s | thresholds_min=(24h=%s, 48h=%s, 72h=%s)",
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

        cls._stop_event = asyncio.Event()
        cls._bot = bot
        cls._task = asyncio.create_task(cls._runner())
        logger.info(
            "DRIP worker started (interval=%ss)",
            DRIP_CHECK_INTERVAL_SEC,
        )

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
        except asyncio.CancelledError:
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
                    logger.debug("DRIP worker has no bot instance; sleeping")
                else:
                    iteration += 1
                    iteration_started_at = datetime.utcnow()
                    logger.info(
                        "DRIP scan start | iteration=%s | utc=%s",
                        iteration,
                        _format_dt(iteration_started_at),
                    )
                    stage_candidates: dict[tuple[str, int], int] = defaultdict(int)
                    stage_sent: dict[tuple[str, int], int] = defaultdict(int)
                    try:
                        snapshots, query_text = await _load_candidates()
                        logger.info(
                            "DRIP selection query | %s",
                            query_text,
                        )
                        logger.info(
                            "DRIP candidates loaded | count=%s",
                            len(snapshots),
                        )
                        for snapshot in snapshots:
                            decisions = await _process_snapshot(bot, snapshot)
                            for cohort, stage, sent in decisions:
                                stage_candidates[(cohort, stage)] += 1
                                if sent:
                                    stage_sent[(cohort, stage)] += 1
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("DRIP worker iteration failed: %s", exc)
                    else:
                        for cohort in _COHORTS:
                            for stage in (1, 2, 3):
                                key = (cohort, stage)
                                logger.info(
                                    "DRIP stage stats | cohort=%s | stage=%s | ready=%s | sent=%s",
                                    cohort,
                                    _STAGE_LABELS.get(stage, stage),
                                    stage_candidates.get(key, 0),
                                    stage_sent.get(key, 0),
                                )
                        duration = datetime.utcnow() - iteration_started_at
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
        except asyncio.CancelledError:
            logger.debug("DRIP worker task cancelled")
            raise

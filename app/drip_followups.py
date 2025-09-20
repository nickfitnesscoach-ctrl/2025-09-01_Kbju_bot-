"""Фоновая рассылка догоняющих кейсов по неактивности."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

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


@dataclass(slots=True)
class DripUserSnapshot:
    tg_id: int
    gender: str | None
    funnel_status: str | None
    last_activity_at: datetime
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


def _is_in_tips_cohort(snapshot: DripUserSnapshot) -> bool:
    status = _normalize_status(snapshot.funnel_status)
    if _is_finished_status(status):
        return False
    return status == FUNNEL_STATUSES["coldlead_delayed"]


def _is_in_stalled_cohort(snapshot: DripUserSnapshot) -> bool:
    if not snapshot.has_started:
        return False
    status = _normalize_status(snapshot.funnel_status)
    if _is_finished_status(status):
        return False
    if status == FUNNEL_STATUSES["coldlead_delayed"]:
        return False
    return True


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


async def _load_candidates() -> list[DripUserSnapshot]:
    async with async_session() as session:
        result = await session.scalars(
            select(User).where(
                User.last_activity_at.isnot(None),
                or_(User.drip_stage_stalled < 3, User.drip_stage_tips < 3),
            )
        )
        users = result.all()

    snapshots: list[DripUserSnapshot] = []
    for user in users:
        if not user.last_activity_at:
            continue
        snapshots.append(
            DripUserSnapshot(
                tg_id=user.tg_id,
                gender=user.gender,
                funnel_status=user.funnel_status,
                last_activity_at=user.last_activity_at,
                drip_stage_stalled=int(getattr(user, "drip_stage_stalled", 0) or 0),
                drip_stage_tips=int(getattr(user, "drip_stage_tips", 0) or 0),
                has_started=_has_started(user),
            )
        )
    return snapshots


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
        await update_drip_stage(snapshot.tg_id, cohort=cohort, stage=stage_to_set)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DRIP stage update failed for user %s (cohort=%s): %s",
            snapshot.tg_id,
            cohort,
            exc,
        )

    return True


def _resolve_cohorts(snapshot: DripUserSnapshot) -> Iterable[str]:
    cohorts: list[str] = []
    if _is_in_tips_cohort(snapshot):
        cohorts.append("tips")
    if _is_in_stalled_cohort(snapshot):
        cohorts.append("stalled")
    return cohorts


async def _process_snapshot(bot: Bot, snapshot: DripUserSnapshot) -> None:
    if snapshot.tg_id is None:
        return

    last_activity = snapshot.last_activity_at
    if not last_activity:
        return

    elapsed_seconds = (datetime.utcnow() - last_activity).total_seconds()
    if elapsed_seconds < 0:
        return

    elapsed_minutes = elapsed_seconds / 60.0
    for cohort in _resolve_cohorts(snapshot):
        stage_attr = "drip_stage_stalled" if cohort == "stalled" else "drip_stage_tips"
        current_stage = int(getattr(snapshot, stage_attr, 0) or 0)
        if current_stage >= 3:
            continue

        stage_to_set = _determine_next_stage(current_stage, elapsed_minutes)
        if not stage_to_set or stage_to_set <= current_stage:
            continue

        sent = await _send_followup(bot, snapshot, cohort, stage_to_set)
        if sent:
            setattr(snapshot, stage_attr, stage_to_set)


class DripFollowupService:
    """Периодический сканер пользователей для отправки кейсов."""

    _task: asyncio.Task | None = None
    _stop_event: asyncio.Event | None = None
    _bot: Bot | None = None

    @classmethod
    def start(cls, bot: Bot) -> None:
        if not ENABLE_DRIP_FOLLOWUPS:
            logger.info("DRIP follow-ups disabled; background worker not started")
            return

        if cls._task and not cls._task.done():
            logger.debug("DRIP follow-up worker already running")
            return

        cls._stop_event = asyncio.Event()
        cls._bot = bot
        cls._task = asyncio.create_task(cls._runner())
        logger.info(
            "DRIP worker started (interval=%ss)",
            DRIP_CHECK_INTERVAL_SEC,
        )

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
        try:
            while True:
                if cls._stop_event.is_set():
                    break

                bot = cls._bot
                if not bot:
                    logger.debug("DRIP worker has no bot instance; sleeping")
                else:
                    try:
                        snapshots = await _load_candidates()
                        for snapshot in snapshots:
                            await _process_snapshot(bot, snapshot)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("DRIP worker iteration failed: %s", exc)

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

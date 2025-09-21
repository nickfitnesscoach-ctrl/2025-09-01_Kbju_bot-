"""KBJU calculation flow and subsequent funnel handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.calculator import KBJUCalculator, get_activity_description, get_goal_description
from app.constants import (
    DEFAULT_CALCULATED_TIMER_DELAY,
    DELAYED_OFFER_DELAY,
    FUNNEL_STATUSES,
    PRIORITY_SCORES,
    VALIDATION_LIMITS,
)
from app.database.requests import get_user, update_user_data, update_user_status
from app.features import CHECK_CALLBACK_DATA, ensure_subscription_and_continue
from app.keyboards import (
    activity_keyboard,
    back_to_menu,
    consultation_contact_keyboard,
    delayed_offer_keyboard,
    gender_keyboard,
    goal_keyboard,
    priority_keyboard,
)
from app.states import KBJUStates
from app.texts import get_button_text, get_text
from app.webhook import TimerService, WebhookService
from config import CHANNEL_URL
from utils.notifications import notify_lead_card

from .shared import error_handler, rate_limit, safe_db_operation, sanitize_text, track_user_activity

logger = logging.getLogger(__name__)


ACTIVITY_INPUT_MAP: dict[str, str] = {
    "min": "low",
    "low": "low",
    "medium": "moderate",
    "high": "high",
}


_delayed_offer_tasks: dict[int, asyncio.Task] = {}


def register(router: Router) -> None:
    router.callback_query.register(start_kbju_flow, F.data == "start_kbju")
    router.callback_query.register(subscription_gate_check, F.data == CHECK_CALLBACK_DATA)
    router.callback_query.register(resume_calculation, F.data == "resume_calc")
    router.callback_query.register(process_gender, F.data.startswith("gender_"))
    router.message.register(process_age, KBJUStates.waiting_age)
    router.message.register(process_weight, KBJUStates.waiting_weight)
    router.message.register(process_height, KBJUStates.waiting_height)
    router.callback_query.register(process_activity, F.data.startswith("activity_"))
    router.callback_query.register(process_goal, F.data.startswith("goal_"))
    router.callback_query.register(process_delayed_yes, F.data == "delayed_yes")
    router.callback_query.register(process_delayed_no, F.data == "delayed_no")
    router.callback_query.register(process_lead_request, F.data == "send_lead")
    router.callback_query.register(process_priority, F.data.startswith("priority_"))
    router.callback_query.register(process_cold_lead, F.data == "funnel_cold")


async def start_funnel_timer(user_id: int) -> None:
    await TimerService.start_calculated_timer(user_id, delay_minutes=DEFAULT_CALCULATED_TIMER_DELAY)


async def _restart_stalled_reminder(user_id: int) -> None:
    try:
        TimerService.cancel_stalled_timer(user_id)
        await TimerService.start_stalled_timer(user_id)
    except Exception as exc:  # noqa: BLE001 - log only
        logger.exception("Failed to restart stalled reminder for user %s: %s", user_id, exc)


async def _cancel_stalled_reminder(user_id: int) -> None:
    try:
        TimerService.cancel_stalled_timer(user_id)
    except Exception as exc:  # noqa: BLE001 - log only
        logger.exception("Failed to cancel stalled reminder for user %s: %s", user_id, exc)


async def _start_kbju_flow_inner(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass
    await _cancel_stalled_reminder(callback.from_user.id)

    await callback.message.edit_text(
        get_text("kbju_start"),
        reply_markup=gender_keyboard(),
        parse_mode="HTML",
    )
    await _restart_stalled_reminder(callback.from_user.id)


def _activity_label_from_buttons(raw: str) -> str:
    return get_button_text(f"activity_{raw}")


def get_advice_by_goal(goal: str) -> str:
    return get_text(f"advice.{goal}")


async def calculate_and_save_kbju(user_id: int, user_data: dict[str, Any]) -> dict[str, int]:
    kbju = KBJUCalculator.calculate_kbju(
        gender=user_data["gender"],
        age=user_data["age"],
        weight=user_data["weight"],
        height=user_data["height"],
        activity=user_data["activity"],
        goal=user_data["goal"],
    )

    await update_user_data(
        tg_id=user_id,
        **user_data,
        **kbju,
        funnel_status=FUNNEL_STATUSES["calculated"],
        calculated_at=datetime.utcnow(),
        priority_score=PRIORITY_SCORES["new"],
    )

    lead_payload = {
        "tg_id": user_id,
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "goal": user_data.get("goal"),
        "calories": kbju.get("calories"),
    }

    asyncio.create_task(notify_lead_card(lead_payload))

    return kbju


def _user_to_dict(user: Any) -> dict[str, Any]:
    if not user:
        return {}
    return {
        "tg_id": user.tg_id or 0,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "gender": user.gender or "",
        "age": user.age or 0,
        "weight": float(user.weight or 0.0),
        "height": int(user.height or 0),
        "activity": user.activity or "",
        "goal": user.goal or "",
        "calories": int(user.calories or 0),
        "proteins": int(user.proteins or 0),
        "fats": int(user.fats or 0),
        "carbs": int(user.carbs or 0),
        "funnel_status": user.funnel_status or "",
        "priority": user.priority or "",
        "priority_score": user.priority_score or 0,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "calculated_at": user.calculated_at.isoformat() if user.calculated_at else None,
    }


async def show_kbju_results(callback: CallbackQuery, kbju: dict[str, int], goal: str) -> None:
    await callback.message.edit_text(
        get_text(
            "kbju_result",
            goal_text=get_goal_description(goal),
            calories=kbju["calories"],
            proteins=kbju["proteins"],
            fats=kbju["fats"],
            carbs=kbju["carbs"],
        ),
        parse_mode="HTML",
    )


async def send_delayed_offer(user_id: int, chat_id: int) -> None:
    from aiogram import Bot
    from config import TOKEN

    bot: Bot | None = None
    try:
        await asyncio.sleep(DELAYED_OFFER_DELAY)
        bot = Bot(token=TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("delayed_offer"),
            reply_markup=delayed_offer_keyboard(),
            parse_mode="HTML",
        )
    except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
        raise
    except Exception as exc:  # noqa: BLE001 - do not break the flow
        logger.error("Error sending delayed offer to %s: %s", user_id, exc)
    finally:
        if bot:
            await bot.session.close()
        _delayed_offer_tasks.pop(user_id, None)


def schedule_delayed_offer(user_id: int, chat_id: int) -> None:
    cancel_delayed_offer(user_id)
    task = asyncio.create_task(send_delayed_offer(user_id, chat_id))
    _delayed_offer_tasks[user_id] = task


def cancel_delayed_offer(user_id: int) -> None:
    task = _delayed_offer_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()


@rate_limit
@error_handler
@track_user_activity("start_kbju_flow")
async def start_kbju_flow(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message):
        return

    await _start_kbju_flow_inner(callback)
    await callback.answer()


@rate_limit
@error_handler
async def subscription_gate_check(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message):
        return

    await ensure_subscription_and_continue(
        callback.bot,
        callback.from_user.id,
        callback,
        on_success=lambda: _start_kbju_flow_inner(callback),
    )


@rate_limit
@error_handler
@track_user_activity("resume_calculation")
async def resume_calculation(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message):
        return

    user_id = callback.from_user.id
    await _cancel_stalled_reminder(user_id)
    await state.clear()
    await _start_kbju_flow_inner(callback)
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_gender")
async def process_gender(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message and callback.data):
        return

    try:
        gender = callback.data.split("_", 1)[1]
        if gender not in {"male", "female"}:
            return

        persist_result = await safe_db_operation(
            update_user_data,
            callback.from_user.id,
            gender=gender,
        )
        if persist_result is False:
            logger.warning("Failed to persist gender for user %s", callback.from_user.id)

        await state.update_data(gender=gender)

        await callback.message.edit_text(get_text("questions.age"), parse_mode="HTML")
        await state.set_state(KBJUStates.waiting_age)
        await _restart_stalled_reminder(callback.from_user.id)
        await callback.answer()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gender processing error: %s", exc)
        await callback.answer(get_text("errors.processing"))


@rate_limit
@error_handler
@track_user_activity("process_age")
async def process_age(message: Message, state: FSMContext) -> None:
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        age = int(text)
        limits = VALIDATION_LIMITS["age"]
        if limits["min"] <= age <= limits["max"]:
            await state.update_data(age=age)
            await message.answer(get_text("questions.weight", age=age), parse_mode="HTML")
            await state.set_state(KBJUStates.waiting_weight)
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.age_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.age_invalid"), parse_mode="HTML")


@rate_limit
@error_handler
@track_user_activity("process_weight")
async def process_weight(message: Message, state: FSMContext) -> None:
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        weight = float(text.replace(",", "."))
        limits = VALIDATION_LIMITS["weight"]
        if limits["min"] <= weight <= limits["max"]:
            await state.update_data(weight=weight)
            await message.answer(get_text("questions.height", weight=weight), parse_mode="HTML")
            await state.set_state(KBJUStates.waiting_height)
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.weight_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.weight_invalid"), parse_mode="HTML")


@rate_limit
@error_handler
@track_user_activity("process_height")
async def process_height(message: Message, state: FSMContext) -> None:
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        height = int(text)
        limits = VALIDATION_LIMITS["height"]
        if limits["min"] <= height <= limits["max"]:
            await state.update_data(height=height)
            await message.answer(
                get_text("questions.activity", height=height),
                reply_markup=activity_keyboard(),
                parse_mode="HTML",
            )
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.height_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.height_invalid"), parse_mode="HTML")


@rate_limit
@error_handler
@track_user_activity("process_activity")
async def process_activity(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message and callback.data):
        return

    raw = callback.data.split("_", 1)[1]
    activity = ACTIVITY_INPUT_MAP.get(raw, "moderate")
    await state.update_data(activity=activity)

    activity_text = _activity_label_from_buttons(raw)
    await callback.message.edit_text(
        get_text("questions.goal", activity_text=activity_text),
        reply_markup=goal_keyboard(),
        parse_mode="HTML",
    )
    await _restart_stalled_reminder(callback.from_user.id)
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_goal")
async def process_goal(callback: CallbackQuery, state: FSMContext) -> None:
    if not (callback.from_user and callback.message and callback.data):
        return

    await ensure_subscription_and_continue(
        callback.bot,
        callback.from_user.id,
        callback,
        on_success=lambda: _process_goal_after_subscription(callback, state),
    )


async def _process_goal_after_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return

    try:
        goal = callback.data.split("_", 1)[1]
        data = await state.get_data()
        data["goal"] = goal

        kbju = await calculate_and_save_kbju(callback.from_user.id, data)
        await _cancel_stalled_reminder(callback.from_user.id)

        asyncio.create_task(start_funnel_timer(callback.from_user.id))

        await show_kbju_results(callback, kbju, goal)

        user_data = await get_user(callback.from_user.id)
        if user_data:
            logger.info(
                "[Webhook] Sending calculated lead: %s (status %s)",
                user_data.tg_id,
                user_data.funnel_status,
            )
            await WebhookService.send_calculated_lead(_user_to_dict(user_data))
        else:
            logger.warning(
                "[Webhook] Failed to load user %s for calculated webhook", callback.from_user.id
            )

        if callback.message:
            schedule_delayed_offer(callback.from_user.id, callback.message.chat.id)

        await state.clear()
    except Exception as exc:  # noqa: BLE001
        logger.exception("process_goal error: %s", exc)
        try:
            await callback.message.edit_text(
                get_text("errors.calculation_error"),
                reply_markup=back_to_menu(),
                parse_mode="HTML",
            )
            await state.clear()
        except Exception as nested_exc:  # noqa: BLE001
            logger.exception("Failed to send calculation error message: %s", nested_exc)


@rate_limit
@error_handler
@track_user_activity("process_delayed_yes")
async def process_delayed_yes(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass
    await _cancel_stalled_reminder(callback.from_user.id)

    await callback.message.edit_text(
        get_text("hot_lead_priorities"),
        reply_markup=priority_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_delayed_no")
async def process_delayed_no(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    await _cancel_stalled_reminder(callback.from_user.id)
    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["coldlead_delayed"],
        priority_score=PRIORITY_SCORES["coldlead_delayed"],
    )

    user_data = await get_user(callback.from_user.id)
    if user_data:
        await WebhookService.send_cold_lead(_user_to_dict(user_data))

    advice_text = get_advice_by_goal(user_data.goal if user_data else "maintenance")

    await callback.message.edit_text(
        get_text(
            "cold_lead_advice",
            advice_text=advice_text,
            channel_url=CHANNEL_URL or get_text("defaults.channel_username"),
        ),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_lead_request")
async def process_lead_request(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    user_before = await get_user(callback.from_user.id)
    already_hot_lead = bool(
        user_before and str(user_before.funnel_status or "").startswith("hotlead_")
    )

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        logger.debug("Failed to cancel timer for user %s", callback.from_user.id, exc_info=True)
    await _cancel_stalled_reminder(callback.from_user.id)

    cancel_delayed_offer(callback.from_user.id)

    updated_user = await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["hotlead_consultation"],
        priority_score=PRIORITY_SCORES["consultation_request"],
    )

    user_record = updated_user or await get_user(callback.from_user.id) or user_before

    if user_record and not already_hot_lead:
        try:
            await WebhookService.send_hot_lead(_user_to_dict(user_record), "consultation_request")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to send hot lead webhook for user %s: %s",
                callback.from_user.id,
                exc,
            )

    await callback.message.edit_text(
        get_text(
            "hot_lead_success",
            user_id=callback.from_user.id,
            username=callback.from_user.username or get_text("fallbacks.username_unknown"),
        ),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_priority")
async def process_priority(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message and callback.data):
        return

    priority = callback.data.split("_", 1)[1]

    await update_user_data(
        tg_id=callback.from_user.id,
        priority=priority,
    )

    await callback.message.edit_text(
        get_text("consultation_offer"),
        reply_markup=consultation_contact_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_cold_lead")
async def process_cold_lead(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass
    await _cancel_stalled_reminder(callback.from_user.id)

    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["coldlead"],
        priority_score=PRIORITY_SCORES["coldlead"],
    )

    user_data = await get_user(callback.from_user.id)
    if user_data:
        await WebhookService.send_cold_lead(_user_to_dict(user_data))

    advice_text = get_advice_by_goal(user_data.goal if user_data else "maintenance")

    await callback.message.edit_text(
        get_text(
            "cold_lead_advice",
            advice_text=advice_text,
            channel_url=CHANNEL_URL or get_text("defaults.channel_username"),
        ),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()



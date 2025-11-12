"""KBJU calculation flow and subsequent funnel handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.calculator import KBJUCalculator, get_activity_description, get_goal_description
from app.constants import (
    DEFAULT_CALCULATED_TIMER_DELAY,
    FUNNEL_STATUSES,
    VALIDATION_LIMITS,
)
from app.database.requests import get_user, update_user_data, update_user_status
from app.features import CHECK_CALLBACK_DATA, ensure_subscription_and_continue
from app.keyboards import (
    activity_keyboard,
    back_to_menu,
    delayed_offer_keyboard,
    gender_keyboard,
    goal_keyboard,
    body_type_keyboard,
    timezone_keyboard,
    subscription_check_keyboard,
)
from app.states import KBJUStates
from app.texts import get_button_text, get_text
from app.webhook import TimerService, WebhookService

from .shared import error_handler, rate_limit, safe_db_operation, sanitize_text, track_user_activity

logger = logging.getLogger(__name__)


ACTIVITY_INPUT_MAP: dict[str, str] = {
    "min": "low",
    "low": "low",
    "medium": "moderate",
    "high": "high",
}


def register(router: Router) -> None:
    router.callback_query.register(start_kbju_flow, F.data == "start_kbju")
    router.callback_query.register(subscription_gate_check, F.data == CHECK_CALLBACK_DATA)
    router.callback_query.register(resume_calculation, F.data == "resume_calc")
    router.callback_query.register(process_gender, F.data.startswith("gender_"))
    router.message.register(process_age, KBJUStates.waiting_age)
    router.message.register(process_weight, KBJUStates.waiting_weight)
    router.message.register(process_height, KBJUStates.waiting_height)
    router.message.register(process_target_weight, KBJUStates.waiting_target_weight)
    router.callback_query.register(process_current_body_type, F.data.startswith("body_current_"))
    router.callback_query.register(process_target_body_type, F.data.startswith("body_target_"))
    router.callback_query.register(process_timezone, F.data.startswith("tz_"))
    router.callback_query.register(process_activity, F.data.startswith("activity_"))
    router.callback_query.register(process_goal, F.data.startswith("goal_"))
    router.callback_query.register(process_delayed_yes, F.data == "delayed_yes")
    router.callback_query.register(process_lead_request, F.data == "send_lead")


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


def _cancel_calculated_timer(user_id: int, *, context: str) -> None:
    """Отменить таймер расчёта и вывести отладочную информацию."""

    try:
        TimerService.cancel_timer(user_id)
    except Exception as exc:  # noqa: BLE001 - log only
        logger.debug(
            "Failed to cancel calculated timer for user %s in %s: %s",
            user_id,
            context,
            exc,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )


async def _start_kbju_flow_inner(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    _cancel_calculated_timer(callback.from_user.id, context="start_kbju_flow")
    await _cancel_stalled_reminder(callback.from_user.id)

    await callback.message.edit_text(
        get_text("kbju_start"),
        reply_markup=gender_keyboard(),
        parse_mode="HTML",
    )
    await _restart_stalled_reminder(callback.from_user.id)


def _activity_label_from_buttons(raw: str) -> str:
    return get_button_text(f"activity_{raw}")


async def calculate_and_save_kbju(
    user_id: int, user_data: dict[str, Any]
) -> dict[str, int | str]:
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
    )

    return kbju


async def show_kbju_results(
    callback: CallbackQuery, kbju: dict[str, int | str], goal: str
) -> None:
    result_text = get_text(
        "kbju_result",
        goal_text=get_goal_description(goal),
        calories=kbju["calories"],
        proteins=kbju["proteins"],
        fats=kbju["fats"],
        carbs=kbju["carbs"],
    )

    if kbju.get("calories_adjusted_reason") == "carbs_min":
        result_text = "\n\n".join(
            [
                result_text,
                get_text(
                    "kbju_result_calories_adjusted",
                    calories=kbju["calories"],
                    calories_initial=kbju.get("calories_initial", kbju["calories"]),
                ),
            ]
        )

    await callback.message.edit_text(result_text, parse_mode="HTML")


async def send_diagnostics_offer_message(message: Message) -> None:
    await message.answer(
        get_text("delayed_offer"),
        reply_markup=delayed_offer_keyboard(),
        parse_mode="HTML",
    )


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
            # 🆕 Переходим к вопросу о желаемом весе
            await message.answer(
                get_text("questions.target_weight", height=height),
                parse_mode="HTML"
            )
            await state.set_state(KBJUStates.waiting_target_weight)
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.height_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.height_invalid"), parse_mode="HTML")


@rate_limit
@error_handler
@track_user_activity("process_target_weight")
async def process_target_weight(message: Message, state: FSMContext) -> None:
    """Обработка желаемого веса и показ текущей фигуры"""
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        target_weight = float(text.replace(',', '.'))
        limits = VALIDATION_LIMITS["weight"]
        if limits["min"] <= target_weight <= limits["max"]:
            await state.update_data(target_weight=target_weight)

            # Получаем пол пользователя
            data = await state.get_data()
            gender = data.get('gender', 'male')

            # Показываем фото текущих фигур
            await show_body_type_photos(message, state, gender, 'current')
        else:
            await message.answer(get_text("errors.target_weight_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.target_weight_invalid"), parse_mode="HTML")


async def show_body_type_photos(
    message: Message,
    state: FSMContext,
    gender: str,
    category: str  # 'current' или 'target'
) -> None:
    """Показать фотографии типов фигур"""
    from app.database.requests import get_body_type_images_by_category
    from aiogram.types import InputMediaPhoto

    # Загружаем изображения из БД
    images = await get_body_type_images_by_category(gender, category)

    if not images:
        # Если фото еще не загружены, пропускаем
        await message.answer(get_text("errors.body_images_not_uploaded"), parse_mode="HTML")

        # Переходим к следующему вопросу
        if category == 'current':
            # Пропускаем target_body_type тоже
            await message.answer(
                get_text("questions.timezone"),
                reply_markup=timezone_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(KBJUStates.waiting_timezone)
        else:
            await message.answer(
                get_text("questions.timezone"),
                reply_markup=timezone_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(KBJUStates.waiting_timezone)
        return

    # Отправляем медиа-группу (до 4 фото)
    media_group = [
        InputMediaPhoto(
            media=img.file_id,
            caption=img.caption or f"Тип {img.type_number}"
        )
        for img in images[:4]
    ]

    try:
        await message.answer_media_group(media_group)
    except Exception as exc:
        logger.warning(f"Failed to send media group: {exc}")
        # Продолжаем без фото

    # Кнопки выбора
    question_key = "questions.current_body_type" if category == 'current' else "questions.target_body_type"
    
    # Получаем текст вопроса
    data = await state.get_data()
    format_kwargs = {}
    if category == 'target':
        format_kwargs['current_body_type'] = data.get('current_body_type', '?')
    else:
        format_kwargs['target_weight'] = data.get('target_weight', '?')
    
    question_text = get_text(question_key, **format_kwargs)
    
    # Создаем клавиатуру с callback_data в зависимости от категории
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    callback_prefix = f"body_{category}_"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"{callback_prefix}1"),
            InlineKeyboardButton(text="2", callback_data=f"{callback_prefix}2"),
            InlineKeyboardButton(text="3", callback_data=f"{callback_prefix}3"),
            InlineKeyboardButton(text="4", callback_data=f"{callback_prefix}4"),
        ]
    ])

    await message.answer(question_text, reply_markup=keyboard, parse_mode="HTML")

    # Устанавливаем состояние
    if category == 'current':
        await state.set_state(KBJUStates.waiting_current_body_type)
    else:
        await state.set_state(KBJUStates.waiting_target_body_type)


@rate_limit
@error_handler
@track_user_activity("process_current_body_type")
async def process_current_body_type(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """Обработка выбора текущей фигуры и показ желаемых"""
    if not (callback.from_user and callback.message and callback.data):
        return

    type_number = callback.data.split("_")[-1]  # "1", "2", "3", "4"
    await state.update_data(current_body_type=type_number)
    await callback.answer()

    # Получаем пол
    data = await state.get_data()
    gender = data.get('gender', 'male')

    # Показываем фото желаемых фигур
    await show_body_type_photos(callback.message, state, gender, 'target')


@rate_limit
@error_handler
@track_user_activity("process_target_body_type")
async def process_target_body_type(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """Обработка выбора желаемой фигуры и вопрос о часовом поясе"""
    if not (callback.from_user and callback.message and callback.data):
        return

    type_number = callback.data.split("_")[-1]
    await state.update_data(target_body_type=type_number)
    await callback.answer()

    # Показываем часовые пояса
    if callback.message:
        await callback.message.answer(
            get_text("questions.timezone"),
            reply_markup=timezone_keyboard(),
            parse_mode="HTML"
        )
    await state.set_state(KBJUStates.waiting_timezone)


@rate_limit
@error_handler
@track_user_activity("process_timezone")
async def process_timezone(
    callback: CallbackQuery,
    state: FSMContext
) -> None:
    """Обработка часового пояса и переход к вопросу об активности"""
    if not (callback.from_user and callback.message and callback.data):
        return

    timezone = callback.data.split("_")[1]
    await state.update_data(timezone=timezone)
    await callback.answer()

    # Получаем название часового пояса
    from app.texts import get_timezone_description
    timezone_text = get_timezone_description(timezone)

    # Переходим к вопросу об активности
    if callback.message:
        await callback.message.answer(
            get_text("questions.activity", timezone_text=timezone_text),
            reply_markup=activity_keyboard(),
            parse_mode="HTML"
        )
    await _restart_stalled_reminder(callback.from_user.id)


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


async def generate_and_show_ai_recommendations(
    message: Message,
    user_id: int,
    user_data: dict,
    kbju: dict
) -> None:
    """
    Генерировать и показать AI-рекомендации
    
    Args:
        message: Сообщение пользователя
        user_id: Telegram ID пользователя
        user_data: Данные из state (пол, возраст, вес, и т.д.)
        kbju: Рассчитанные КБЖУ
    """
    from app.services.ai_recommendations import generate_ai_recommendations
    from app.database.requests import update_user
    from datetime import datetime

    # Показываем сообщение о генерации
    await message.answer(get_text("ai.generating"), parse_mode="HTML")

    try:
        # Собираем полные данные для AI
        full_data = {**user_data, **kbju}
        
        # Генерируем AI-рекомендации
        ai_text = await generate_ai_recommendations(full_data)

        # Сохраняем AI-рекомендации в БД
        db_user = await get_user(user_id)
        if db_user:
            db_user.ai_recommendations = ai_text
            db_user.ai_generated_at = datetime.utcnow()
            await update_user(db_user)
            logger.info(f"AI recommendations saved for user {user_id}")

        # Показываем рекомендации
        await message.answer(
            f"🤖 <b>Персональные рекомендации:</b>\n\n{ai_text}",
            parse_mode="HTML"
        )
        logger.info(f"AI recommendations displayed to user {user_id}")

    except Exception as exc:
        logger.exception(f"Failed to generate AI recommendations for user {user_id}: {exc}")
        await message.answer(get_text("errors.ai_generation_error"), parse_mode="HTML")


async def show_trainer_offer(message: Message) -> None:
    """
    Показать оффер тренера с кнопкой "Написать тренеру"
    
    Args:
        message: Сообщение пользователя
    """
    from app.database.requests import get_setting
    from app.constants import DEFAULT_OFFER_TEXT, SETTING_OFFER_TEXT
    from config import ADMIN_CHAT_ID
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # Получаем текст оффера из настроек (редактируемый в админке)
    offer_text = await get_setting(SETTING_OFFER_TEXT)
    if not offer_text:
        offer_text = DEFAULT_OFFER_TEXT

    # Получаем username админа/тренера для кнопки
    trainer_username = None
    if ADMIN_CHAT_ID and message.bot:
        try:
            admin = await message.bot.get_chat(ADMIN_CHAT_ID)
            if hasattr(admin, 'username') and admin.username:
                trainer_username = admin.username
        except Exception as exc:
            logger.warning(f"Failed to get admin username: {exc}")

    # Создаем кнопку
    keyboard = None
    if trainer_username:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✉️ Написать тренеру",
                url=f"https://t.me/{trainer_username}"
            )]
        ])

    await message.answer(offer_text, reply_markup=keyboard, parse_mode="HTML")
    logger.info(f"Trainer offer shown to user {message.from_user.id if message.from_user else 'unknown'}")


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

        # 🆕 Генерируем AI-рекомендации
        await generate_and_show_ai_recommendations(
            callback.message,
            callback.from_user.id,
            data,
            kbju
        )

        user_data = await get_user(callback.from_user.id)
        if user_data:
            logger.info(
                "[Webhook] Sending calculated lead: %s (status %s)",
                user_data.tg_id,
                user_data.funnel_status,
            )
            await WebhookService.send_calculated_lead(
                WebhookService.serialize_user(user_data)
            )
        else:
            logger.warning(
                "[Webhook] Failed to load user %s for calculated webhook", callback.from_user.id
            )

        # 🆕 Показываем оффер тренера
        if callback.message:
            await show_trainer_offer(callback.message)

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

    _cancel_calculated_timer(callback.from_user.id, context="process_delayed_yes")
    await _cancel_stalled_reminder(callback.from_user.id)

    await _handle_diagnostic_request(callback)
    await callback.answer()


@rate_limit
@error_handler
@track_user_activity("process_lead_request")
async def process_lead_request(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    _cancel_calculated_timer(callback.from_user.id, context="process_lead_request")
    await _cancel_stalled_reminder(callback.from_user.id)

    success_text = get_text("hot_lead_success")

    async def _send_success_message() -> None:
        try:
            await callback.message.edit_reply_markup()
        except TelegramBadRequest:
            pass
        await callback.message.answer(success_text, parse_mode="HTML")

    await _register_consultation_request(callback.from_user.id)
    await _send_success_message()
    await callback.answer()


async def _register_consultation_request(user_id: int) -> None:
    user_before = await get_user(user_id)
    already_hot_lead = bool(
        user_before and str(user_before.funnel_status or "").startswith("hotlead_")
    )

    updated_user = await update_user_status(
        tg_id=user_id,
        status=FUNNEL_STATUSES["hotlead_consultation"],
    )

    user_record = updated_user or await get_user(user_id) or user_before

    if user_record and not already_hot_lead:
        try:
            await WebhookService.send_hot_lead(
                WebhookService.serialize_user(user_record)
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to send hot lead webhook for user %s: %s",
                user_id,
                exc,
            )


async def _handle_diagnostic_request(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    await _register_consultation_request(callback.from_user.id)

    confirmation_text = get_text("hot_lead_success")
    await callback.message.answer(confirmation_text, parse_mode="HTML")


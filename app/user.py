"""
Основной flow для пользователей Fitness Bot
Регистрация → КБЖУ → воронка → вебхуки. Все видимые тексты берём из texts_data.json.
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, URLInputFile

from app.calculator import KBJUCalculator, get_activity_description, get_goal_description
from app.constants import (
    USER_REQUESTS_LIMIT,
    USER_REQUESTS_WINDOW,
    DEFAULT_CALCULATED_TIMER_DELAY,
    DELAYED_OFFER_DELAY,
    PRIORITY_SCORES,
    VALIDATION_LIMITS,
    MAX_TEXT_LENGTH,
    DB_OPERATION_TIMEOUT,
    FUNNEL_STATUSES,
)
from app.database.requests import get_user, set_user, update_user_data, update_user_status
from app.keyboards import (
    main_menu,
    gender_keyboard,
    activity_keyboard,
    goal_keyboard,
    priority_keyboard,
    profile_keyboard,
    delayed_offer_keyboard,
    consultation_contact_keyboard,
    back_to_menu,
)
from app.states import KBJUStates
from app.texts import get_text
from app.webhook import TimerService, WebhookService
from config import CHANNEL_URL

logger = logging.getLogger(__name__)

# ---------------------------
# Router
# ---------------------------

user = Router()

# ---------------------------
# Rate limiting (память процесса)
# ---------------------------

_user_requests: Dict[int, list[float]] = {}

def rate_limit(func):
    """Ограничение частоты запросов на пользователя."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Пытаемся взять from_user из первого аргумента (Message/CallbackQuery)
        user_id: Optional[int] = None
        if args and hasattr(args[0], "from_user") and args[0].from_user:
            user_id = args[0].from_user.id

        if user_id:
            now = datetime.utcnow().timestamp()
            bucket = _user_requests.setdefault(user_id, [])
            # чистим старые события
            bucket[:] = [t for t in bucket if now - t < USER_REQUESTS_WINDOW]
            if len(bucket) >= USER_REQUESTS_LIMIT:
                logger.warning("Rate limit exceeded for user %s", user_id)
                return
            bucket.append(now)

        return await func(*args, **kwargs)
    return wrapper


def error_handler(func):
    """Единая обёртка для ловли и корректного ответа на ошибки Telegram/сети."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except TelegramBadRequest as e:
            logger.error("TelegramBadRequest in %s: %s", func.__name__, e)

            # Самый частый «не баг»: попытка отредактировать идентичным текстом
            if "message is not modified" in str(e):
                if args and hasattr(args[0], "answer"):
                    try:
                        await args[0].answer()
                    except (TelegramBadRequest, TelegramNetworkError) as e2:
                        logger.warning("Callback answer failed: %s", e2)
                return

            # Пытаемся отправить новое сообщение вместо редактирования
            if args and hasattr(args[0], "message") and args[0].message:
                try:
                    await args[0].message.answer(
                        get_text("errors.general_error"),
                        reply_markup=back_to_menu(),
                        parse_mode="HTML",
                    )
                except Exception as e3:
                    logger.exception("Unhandled UI error: %s", e3)

        except TelegramRetryAfter as e:
            logger.warning("Rate limited by Telegram: %s", e)
            await asyncio.sleep(e.retry_after)

        except Exception as e:
            logger.exception("Unexpected error in %s: %s", func.__name__, e)
            if args and hasattr(args[0], "message") and args[0].message:
                try:
                    await args[0].message.answer(
                        get_text("errors.general_error"),
                        reply_markup=back_to_menu(),
                        parse_mode="HTML",
                    )
                except Exception as e2:
                    logger.exception("Unhandled UI error: %s", e2)
    return wrapper


# ---------------------------
# Утилиты
# ---------------------------

def sanitize_text(text: Any, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Экранируем HTML и ограничиваем длину для безопасного сохранения в БД/логах."""
    s = "" if text is None else str(text)
    s = html.escape(s)
    return s if len(s) <= max_length else (s[:max_length] + "…")


async def safe_db_operation(operation, *args, **kwargs):
    """Выполнить операцию с БД с таймаутом и логированием ошибок."""
    try:
        return await asyncio.wait_for(operation(*args, **kwargs), timeout=DB_OPERATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("DB timeout: %s", getattr(operation, "__name__", str(operation)))
        return None
    except Exception as e:
        logger.exception("DB error in %s: %s", getattr(operation, "__name__", str(operation)), e)
        return None


def get_advice_by_goal(goal: str) -> str:
    """Советы по ключу цели (weight_loss/maintenance/weight_gain)."""
    return get_text(f"advice.{goal}")


async def calculate_and_save_kbju(user_id: int, user_data: dict) -> dict:
    """Рассчитать КБЖУ и сохранить пользователя с результатами в БД."""
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
    return kbju


async def show_kbju_results(callback: CallbackQuery, kbju: dict, goal: str):
    """Отправить результат расчёта КБЖУ (текст из JSON)."""
    await callback.message.edit_text(
        get_text(
            "kbju_result",
            goal_text=get_goal_description(goal).lower(),
            calories=kbju["calories"],
            proteins=kbju["proteins"],
            fats=kbju["fats"],
            carbs=kbju["carbs"],
        ),
        parse_mode="HTML",
    )


async def start_funnel_timer(user_id: int) -> None:
    """Запланировать переход по воронке после расчёта."""
    await TimerService.start_calculated_timer(user_id, delay_minutes=DEFAULT_CALCULATED_TIMER_DELAY)


async def send_delayed_offer(user_id: int, chat_id: int):
    """Отправить отложенное предложение (через DELAYED_OFFER_DELAY секунд)."""
    from aiogram import Bot  # локальный импорт, чтобы не держать токен в памяти без нужды
    from config import TOKEN

    await asyncio.sleep(DELAYED_OFFER_DELAY)
    try:
        bot = Bot(token=TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("delayed_offer"),
            reply_markup=delayed_offer_keyboard(),
            parse_mode="HTML",
        )
        await bot.session.close()
    except Exception as e:
        logger.error("Error sending delayed offer to %s: %s", user_id, e)


def schedule_delayed_offer(user_id: int, chat_id: int) -> None:
    """Фоново запланировать отправку отложенного предложения."""
    asyncio.create_task(send_delayed_offer(user_id, chat_id))


async def send_welcome_sequence(message: Message):
    """Приветственная последовательность: фото → текст + главное меню."""
    # 1) Фото
    try:
        photo_url = get_text("coach_photo_url")
        await message.answer_photo(photo=URLInputFile(photo_url))
    except Exception as e:
        logger.warning("Welcome photo failed: %s", e)

    # 2) Приветственный текст
    try:
        await message.answer(
            get_text("welcome"),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await message.answer("Добро пожаловать!", reply_markup=main_menu())


# ---------------------------
# Маппинг активности (ввод → расчёт / отображение)
# ---------------------------

ACTIVITY_INPUT_MAP = {
    "min": "low",
    "low": "low",
    "medium": "moderate",
    "high": "high",
}

ACTIVITY_DISPLAY_MAP = {
    "min": "📉 Минимальная",
    "low": "🚶 Низкая",
    "medium": "🏋️ Средняя",
    "high": "🔥 Высокая",
}

# ---------------------------
# Handlers
# ---------------------------

@user.message(CommandStart())
@rate_limit
@error_handler
async def cmd_start(message: Message):
    """Команда /start — регистрируем пользователя и показываем приветствие."""
    if not message.from_user or not message.from_user.id:
        logger.warning("Start without user info")
        return

    username = sanitize_text(message.from_user.username or "", 50)
    first_name = sanitize_text(message.from_user.first_name or "Пользователь", 50)

    result = await safe_db_operation(
        set_user,
        tg_id=message.from_user.id,
        username=username,
        first_name=first_name,
    )
    if result is False:
        await message.answer(get_text("errors.temp_error"), parse_mode="HTML")
        return

    await send_welcome_sequence(message)


@user.callback_query(F.data == "main_menu")
@rate_limit
@error_handler
async def show_main_menu(callback: CallbackQuery):
    """Главное меню."""
    if not (callback.from_user and callback.message):
        return

    await callback.message.edit_text(
        get_text("main_menu"),
        reply_markup=main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data == "profile")
@rate_limit
@error_handler
async def show_profile(callback: CallbackQuery):
    """Профиль пользователя (если есть расчёт)."""
    if not (callback.from_user and callback.message):
        return

    user_data = await safe_db_operation(get_user, callback.from_user.id)
    if not user_data or not user_data.calories:
        await callback.message.edit_text(
            get_text("profile.no_data"),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        goal_text = get_goal_description(user_data.goal or "maintenance")
        activity_text = get_activity_description(user_data.activity or "moderate")

        calc_date = "не указано"
        if user_data.calculated_at:
            try:
                calc_date = user_data.calculated_at.strftime("%d.%m.%Y")
            except Exception:
                pass

        await callback.message.edit_text(
            get_text(
                "profile.template",
                gender_icon="👨" if user_data.gender == "male" else "👩",
                gender_text="Мужской" if user_data.gender == "male" else "Женский",
                age=user_data.age or 0,
                height=user_data.height or 0,
                weight=user_data.weight or 0,
                activity_text=activity_text,
                goal_text=goal_text,
                calories=user_data.calories or 0,
                proteins=user_data.proteins or 0,
                fats=user_data.fats or 0,
                carbs=user_data.carbs or 0,
                calc_date=calc_date,
            ),
            reply_markup=profile_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.exception("Profile formatting error: %s", e)
        await callback.message.edit_text(
            get_text("errors.profile_error"),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()


@user.callback_query(F.data == "start_kbju")
@rate_limit
@error_handler
async def start_kbju_flow(callback: CallbackQuery, state: FSMContext):
    """Старт расчёта КБЖУ."""
    if not (callback.from_user and callback.message):
        return

    # если возвращается — отменяем таймер воронки
    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception as e:
        logger.debug("Timer cancel failed: %s", e)

    await callback.message.edit_text(
        get_text("kbju_start"),
        reply_markup=gender_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data.startswith("gender_"))
@rate_limit
@error_handler
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Пол пользователя."""
    if not (callback.from_user and callback.message and callback.data):
        return

    try:
        gender = callback.data.split("_", 1)[1]  # male/female
        if gender not in {"male", "female"}:
            return
        await state.update_data(gender=gender)

        await callback.message.edit_text(
            get_text("questions.age"),
            parse_mode="HTML",
        )
        await state.set_state(KBJUStates.waiting_age)
        await callback.answer()

    except Exception as e:
        logger.exception("Gender processing error: %s", e)
        await callback.answer("Ошибка обработки данных")


@user.message(KBJUStates.waiting_age)
@rate_limit
@error_handler
async def process_age(message: Message, state: FSMContext):
    """Возраст."""
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        age = int(text)
        if VALIDATION_LIMITS["age"]["min"] <= age <= VALIDATION_LIMITS["age"]["max"]:
            await state.update_data(age=age)
            await message.answer(
                get_text("questions.weight", age=age),
                parse_mode="HTML",
            )
            await state.set_state(KBJUStates.waiting_weight)
        else:
            await message.answer(get_text("errors.age_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.age_invalid"), parse_mode="HTML")


@user.message(KBJUStates.waiting_weight)
@rate_limit
@error_handler
async def process_weight(message: Message, state: FSMContext):
    """Вес."""
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        weight = float(text.replace(",", "."))
        if VALIDATION_LIMITS["weight"]["min"] <= weight <= VALIDATION_LIMITS["weight"]["max"]:
            await state.update_data(weight=weight)
            await message.answer(
                get_text("questions.height", weight=weight),
                parse_mode="HTML",
            )
            await state.set_state(KBJUStates.waiting_height)
        else:
            await message.answer(get_text("errors.weight_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.weight_invalid"), parse_mode="HTML")


@user.message(KBJUStates.waiting_height)
@rate_limit
@error_handler
async def process_height(message: Message, state: FSMContext):
    """Рост."""
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        height = int(text)
        if VALIDATION_LIMITS["height"]["min"] <= height <= VALIDATION_LIMITS["height"]["max"]:
            await state.update_data(height=height)
            await message.answer(
                get_text("questions.activity", height=height),
                reply_markup=activity_keyboard(),
                parse_mode="HTML",
            )
        else:
            await message.answer(get_text("errors.height_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.height_invalid"), parse_mode="HTML")


@user.callback_query(F.data.startswith("activity_"))
@rate_limit
@error_handler
async def process_activity(callback: CallbackQuery, state: FSMContext):
    """Активность."""
    if not (callback.from_user and callback.message and callback.data):
        return

    raw = callback.data.split("_", 1)[1]  # min/low/medium/high
    activity = ACTIVITY_INPUT_MAP.get(raw, "moderate")
    await state.update_data(activity=activity)

    activity_text = ACTIVITY_DISPLAY_MAP.get(raw, "🚶 Умеренная")

    await callback.message.edit_text(
        get_text("questions.goal", activity_text=activity_text),
        reply_markup=goal_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data.startswith("goal_"))
@rate_limit
@error_handler
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Финал — рассчитываем, показываем результат, запускаем таймеры."""
    if not (callback.from_user and callback.message and callback.data):
        return

    try:
        goal = callback.data.split("_", 1)[1]  # weight_loss/maintenance/weight_gain
        data = await state.get_data()
        data["goal"] = goal

        kbju = await calculate_and_save_kbju(callback.from_user.id, data)
        await start_funnel_timer(callback.from_user.id)
        await show_kbju_results(callback, kbju, goal)
        await callback.answer()
        await state.clear()

        schedule_delayed_offer(callback.from_user.id, callback.message.chat.id)

    except Exception as e:
        logger.exception("process_goal error: %s", e)
        await callback.message.edit_text(
            get_text("errors.calculation_error"),
            reply_markup=back_to_menu(),
            parse_mode="HTML",
        )
        await callback.answer()
        await state.clear()


@user.callback_query(F.data == "delayed_yes")
@rate_limit
@error_handler
async def process_delayed_yes(callback: CallbackQuery):
    """Пользователь готов — выбираем приоритет."""
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass

    await callback.message.edit_text(
        get_text("hot_lead_priorities"),
        reply_markup=priority_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data == "delayed_no")
@rate_limit
@error_handler
async def process_delayed_no(callback: CallbackQuery):
    """Пользователь хочет советы — холодный лид (delayed)."""
    if not (callback.from_user and callback.message):
        return

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
        get_text("cold_lead_advice", advice_text=advice_text, channel_url=CHANNEL_URL or "@fitness_channel"),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data == "send_lead")
@rate_limit
@error_handler
async def process_lead_request(callback: CallbackQuery):
    """Оставить заявку (горячий лид)."""
    if not (callback.from_user and callback.message):
        return

    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["hotlead_consultation"],
        priority_score=PRIORITY_SCORES["consultation_request"],
    )

    user_data = await get_user(callback.from_user.id)
    if user_data:
        await WebhookService.send_hot_lead(_user_to_dict(user_data), "consultation_request")

    success_text = get_text(
        "hot_lead_success",
        user_id=callback.from_user.id,
        username=callback.from_user.username or "не указан",
    )

    await callback.message.edit_text(
        success_text,
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data.startswith("priority_"))
@rate_limit
@error_handler
async def process_priority(callback: CallbackQuery):
    """Выбор приоритета (nutrition/training/schedule) → оффер консультации."""
    if not (callback.from_user and callback.message and callback.data):
        return

    priority = callback.data.split("_", 1)[1]

    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["hotlead_delayed"],
        priority=priority,
        priority_score=PRIORITY_SCORES["hotlead_delayed"],
    )

    user_data = await get_user(callback.from_user.id)
    if user_data:
        await WebhookService.send_hot_lead(_user_to_dict(user_data), priority)

    await callback.message.edit_text(
        get_text("consultation_offer"),
        reply_markup=consultation_contact_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data == "funnel_cold")
@rate_limit
@error_handler
async def process_cold_lead(callback: CallbackQuery):
    """Ручной переход в холодные лиды (получить советы)."""
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass

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
        get_text("cold_lead_advice", advice_text=advice_text, channel_url=CHANNEL_URL or "@fitness_channel"),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------
# Helpers
# ---------------------------

def _user_to_dict(user) -> dict:
    """Преобразование ORM-объекта пользователя в плоский dict для webhook."""
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
    }

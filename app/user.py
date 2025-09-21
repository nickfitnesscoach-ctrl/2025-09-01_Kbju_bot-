"""
Основной flow для пользователей Fitness Bot
Регистрация → КБЖУ → воронка → вебхуки.
Все пользовательские тексты и подписи кнопок берём из texts_data.json.
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    URLInputFile,
)

from app.calculator import KBJUCalculator, get_activity_description  # activity пока из helper
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
from app.database.requests import (
    count_started_leads,
    delete_user_by_tg_id,
    get_started_leads,
    get_user,
    set_user,
    update_user_data,
    update_user_status,
    update_last_activity,
)
from app.features import CHECK_CALLBACK_DATA, ensure_subscription_and_continue
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
from app.texts import get_text, get_button_text, get_media_id
from app.webhook import TimerService, WebhookService
from app.contact_requests import contact_request_registry
from config import CHANNEL_URL, ADMIN_CHAT_ID
from utils.notifications import CONTACT_REQUEST_MESSAGE, build_lead_card, notify_lead_card

logger = logging.getLogger(__name__)
user = Router()

LEADS_PAGE_SIZE = 10
DEFAULT_LEADS_WINDOW = "all"
_LEADS_WINDOW_DELTAS: dict[str, timedelta | None] = {
    "all": None,
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
}
_LEADS_WINDOW_LABELS: dict[str, str] = {
    "all": "все",
    "today": "за 24 часа",
    "7d": "за 7 дней",
}

# ---------------------------
# Rate limiting (в памяти процесса)
# ---------------------------

_user_requests: dict[int, list[float]] = {}


def rate_limit(func):
    """Ограничение частоты запросов на пользователя (простая скользящая «ведёрная» схема)."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id: int | None = None
        if args and hasattr(args[0], "from_user") and args[0].from_user:
            user_id = args[0].from_user.id

        if user_id:
            now = datetime.utcnow().timestamp()
            bucket = _user_requests.setdefault(user_id, [])
            bucket[:] = [t for t in bucket if now - t < USER_REQUESTS_WINDOW]
            if len(bucket) >= USER_REQUESTS_LIMIT:
                logger.warning("Rate limit exceeded for user %s", user_id)
                return
            bucket.append(now)

        return await func(*args, **kwargs)
    return wrapper


def error_handler(func):
    """Единая обработка ошибок Telegram/сети с безопасным ответом пользователю."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except TelegramBadRequest as e:
            logger.error("TelegramBadRequest in %s: %s", func.__name__, e)
            # частый случай — «message is not modified»
            if "message is not modified" in str(e):
                if args and hasattr(args[0], "answer"):
                    try:
                        await args[0].answer()
                    except (TelegramBadRequest, TelegramNetworkError) as e2:
                        logger.warning("Callback answer failed: %s", e2)
                return
            # пробуем показать безопасное сообщение
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
    """Экранируем HTML и ограничиваем длину."""
    s = "" if text is None else str(text)
    s = html.escape(s)
    return s if len(s) <= max_length else (s[:max_length] + "…")


async def safe_db_operation(operation, *args, **kwargs):
    """Выполнить операцию с БД с таймаутом и логированием ошибок."""
    try:
        return await asyncio.wait_for(operation(*args, **kwargs), timeout=DB_OPERATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("DB timeout: %s", getattr(operation, "__name__", str(operation)))
        return False
    except Exception as exc:
        logger.exception("DB error in %s: %s", getattr(operation, "__name__", str(operation)), exc)
        return False


async def _touch_user_activity(user_id: int, *, source: str) -> None:
    """Обновить отметку активности и залогировать результат."""

    result = await safe_db_operation(update_last_activity, user_id)
    if result:
        logger.debug("Last activity updated for user %s via %s", user_id, source)
    else:
        logger.debug("Last activity update skipped for user %s via %s", user_id, source)


@user.my_chat_member(F.chat.type == "private")
async def handle_private_chat_member_update(event: ChatMemberUpdated) -> None:
    """Оповестить админа, если пользователь заблокировал бота или вышел из чата."""

    new_status = event.new_chat_member.status
    if new_status not in {ChatMemberStatus.KICKED, ChatMemberStatus.LEFT}:
        return

    lead_user = event.from_user or event.new_chat_member.user
    if not lead_user or not lead_user.id:
        logger.warning("Chat member update without user info: %s", event)
        return

    lead_id = lead_user.id

    db_user = await safe_db_operation(get_user, lead_id)
    if db_user is False:
        logger.warning("Failed to fetch user %s for leave notification", lead_id)
        db_user = None

    if db_user:
        lead_payload: dict[str, Any] = {
            "tg_id": db_user.tg_id,
            "username": getattr(db_user, "username", None),
            "first_name": getattr(db_user, "first_name", None),
            "goal": getattr(db_user, "goal", None),
            "calories": getattr(db_user, "calories", None),
        }
    else:
        lead_payload = {
            "tg_id": lead_id,
            "username": getattr(lead_user, "username", None),
            "first_name": getattr(lead_user, "first_name", None),
            "goal": None,
            "calories": None,
        }

    try:
        await notify_lead_card(lead_payload, title="Лид покинул бот")
        logger.info("Sent leave notification for user %s", lead_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send leave notification for user %s: %s", lead_id, exc)


def _extract_user_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, CallbackQuery) and value.from_user:
            return value.from_user.id
        if isinstance(value, Message) and value.from_user:
            return value.from_user.id
    return None


def track_user_activity(source: str) -> Callable:
    """Декоратор для автоматического обновления last_activity_at."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = _extract_user_id(args, kwargs)
            try:
                return await func(*args, **kwargs)
            finally:
                if user_id:
                    try:
                        await _touch_user_activity(user_id, source=source)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to update last activity for user %s via %s: %s",
                            user_id,
                            source,
                            exc,
                        )

        return wrapper

    return decorator


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

    # Уведомляем админа карточкой с актуальными данными (не блокируем UI)
    lead_payload = {
        "tg_id": user_id,
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "goal": user_data.get("goal"),
        "calories": kbju.get("calories"),
    }
    asyncio.create_task(notify_lead_card(lead_payload))

    return kbju


async def _is_contact_response(message: Message) -> bool:
    """Проверить, является ли сообщение ответом лида на запрос связаться."""
    if not message.from_user:
        return False

    if message.chat.type != "private":
        return False

    if message.reply_to_message and message.reply_to_message.text == CONTACT_REQUEST_MESSAGE:
        return True

    return await contact_request_registry.is_pending(message.from_user.id)


@user.message(_is_contact_response)
async def forward_lead_contact_response(message: Message) -> None:
    """Переслать ответ лида админу после служебного сообщения."""
    if not message.from_user:
        return

    lead_id = message.from_user.id
    logger.info("Forwarding contact reply from lead %s to admin", lead_id)

    if ADMIN_CHAT_ID is None:
        logger.warning("Cannot forward contact reply because ADMIN_CHAT_ID is not configured")
        await _notify_lead_about_failure(message)
        return

    try:
        await message.forward(chat_id=ADMIN_CHAT_ID)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
        logger.error("Failed to forward contact reply from %s: %s", lead_id, exc)
        await _notify_lead_about_failure(message)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while forwarding contact reply from %s: %s", lead_id, exc)
        await _notify_lead_about_failure(message)
        return

    await contact_request_registry.remove(lead_id)

    try:
        await message.answer("Ваше сообщение отправлено администратору.")
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.warning("Failed to confirm contact reply to lead %s: %s", lead_id, exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while confirming contact reply to %s: %s", lead_id, exc)


async def _notify_lead_about_failure(message: Message) -> None:
    """Сообщить пользователю о том, что сообщение не дошло до администратора."""

    try:
        await message.answer("Не удалось отправить сообщение админу, попробуйте позже.")
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.warning("Failed to notify lead about failed contact delivery: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while notifying lead about failed contact delivery: %s", exc)


async def show_kbju_results(callback: CallbackQuery, kbju: dict, goal: str):
    """Отправить результат расчёта КБЖУ (текст из JSON)."""
    await callback.message.edit_text(
        get_text(
            "kbju_result",
            goal_text=get_text(f"goal_descriptions.{goal}"),
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


async def _restart_stalled_reminder(user_id: int) -> None:
    """Перезапустить напоминание о незавершённой анкете."""
    try:
        TimerService.cancel_stalled_timer(user_id)
        await TimerService.start_stalled_timer(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to restart stalled reminder for user %s: %s", user_id, exc)


async def _cancel_stalled_reminder(user_id: int) -> None:
    """Отменить напоминание о незавершённой анкете."""
    try:
        TimerService.cancel_stalled_timer(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to cancel stalled reminder for user %s: %s", user_id, exc)


_delayed_offer_tasks: dict[int, asyncio.Task] = {}


async def send_delayed_offer(user_id: int, chat_id: int):
    """Отложенное сообщение с предложением (через DELAYED_OFFER_DELAY секунд)."""
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
    except asyncio.CancelledError:
        logger.debug("Delayed offer task for user %s was cancelled", user_id)
    except Exception as exc:
        logger.error("Error sending delayed offer to %s: %s", user_id, exc)
    finally:
        if bot:
            await bot.session.close()
        _delayed_offer_tasks.pop(user_id, None)


def schedule_delayed_offer(user_id: int, chat_id: int) -> None:
    """Поставить отложенное сообщение в очередь."""
    cancel_delayed_offer(user_id)
    task = asyncio.create_task(send_delayed_offer(user_id, chat_id))
    _delayed_offer_tasks[user_id] = task


def cancel_delayed_offer(user_id: int) -> None:
    """Отменить запланированную отправку отложенного предложения."""
    task = _delayed_offer_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()


async def send_welcome_sequence(message: Message):
    """Приветствие: фото → текст + главное меню."""
    photo_sent = False
    file_id = get_media_id("coach_photo_file_id")
    if file_id:
        logger.debug("Sending welcome photo via file_id")
        try:
            await message.answer_photo(file_id)
            photo_sent = True
        except Exception as e:
            logger.warning("Welcome photo via file_id failed: %s", e)
    else:
        logger.debug("No cached file_id for welcome photo")

    try:
        if not photo_sent:
            photo_url = get_text("coach_photo_url")
            logger.debug("Sending welcome photo via URL")
            await message.answer_photo(URLInputFile(photo_url))
    except Exception as e:
        logger.warning("Welcome photo via URL failed: %s", e)

    try:
        await message.answer(get_text("welcome"), reply_markup=main_menu(), parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer("Добро пожаловать!", reply_markup=main_menu())


# ---------------------------
# Маппинг активности (callback → калькулятор / отображение)
# ---------------------------

# В callback из клавиатуры приходят: activity_min / activity_low / activity_medium / activity_high
ACTIVITY_INPUT_MAP: dict[str, str] = {
    "min": "low",        # «минимальная» в UI = «low» для формулы
    "low": "low",
    "medium": "moderate",
    "high": "high",
}

# Для текста показываем подписи из JSON-кнопок, чтобы не дублировать строки
def _activity_label_from_buttons(raw: str) -> str:
    return get_button_text(f"activity_{raw}")  # например: activity_min → «📉 Минимальная»


# ---------------------------
# Helper функции
# ---------------------------

def _user_to_dict(user) -> dict:
    """Преобразовать ORM-объект User в dict для webhook."""
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


def _is_admin(user_id: int | None) -> bool:
    """Проверить, является ли пользователь администратором."""

    if user_id is None or ADMIN_CHAT_ID is None:
        return False
    return user_id == ADMIN_CHAT_ID


async def _ensure_admin_access(message: Message) -> bool:
    """Убедиться, что сообщение отправлено администратором."""

    if not message.from_user:
        return False

    if not _is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return False

    return True


def _normalize_leads_window(window: str | None) -> str:
    if not window:
        return DEFAULT_LEADS_WINDOW
    window_key = window.lower()
    if window_key not in _LEADS_WINDOW_DELTAS:
        return DEFAULT_LEADS_WINDOW
    return window_key


def _parse_leads_command_args(args: str | None) -> tuple[int, str]:
    """Разобрать параметры команды /all_leads."""

    page = 1
    window = DEFAULT_LEADS_WINDOW
    if not args:
        return page, window

    for token in args.split():
        token = token.strip()
        if not token:
            continue

        token_lower = token.lower()
        if token_lower in _LEADS_WINDOW_DELTAS:
            window = token_lower
            continue

        try:
            page_value = int(token)
        except ValueError:
            continue

        if page_value > 0:
            page = page_value

    return page, window


def _parse_page_arg(args: str | None) -> int:
    """Извлечь номер страницы из аргументов команды."""

    if not args:
        return 1

    for token in args.split():
        token = token.strip()
        if not token:
            continue

        try:
            page_value = int(token)
        except ValueError:
            continue

        if page_value > 0:
            return page_value

    return 1


def _get_since_for_window(window: str) -> datetime | None:
    delta = _LEADS_WINDOW_DELTAS.get(window)
    if not delta:
        return None
    return datetime.utcnow() - delta


async def _load_leads_page(
    page: int,
    window: str,
) -> tuple[list[Any], int, int, int, str]:
    """Загрузить страницу лидов и вернуть данные для отображения."""

    window_key = _normalize_leads_window(window)
    since = _get_since_for_window(window_key)

    count_raw = await safe_db_operation(count_started_leads, since=since)
    if count_raw is False or count_raw is None:
        raise RuntimeError("Failed to count started leads")

    total_count = int(count_raw)
    if total_count <= 0:
        return [], 0, 0, 1, window_key

    total_pages = (total_count + LEADS_PAGE_SIZE - 1) // LEADS_PAGE_SIZE
    current_page = page if page > 0 else 1
    if current_page > total_pages:
        current_page = total_pages

    offset = (current_page - 1) * LEADS_PAGE_SIZE

    leads_raw = await safe_db_operation(
        get_started_leads,
        offset=offset,
        limit=LEADS_PAGE_SIZE,
        since=since,
    )

    if leads_raw is False or leads_raw is None:
        raise RuntimeError("Failed to load started leads")

    leads_list = list(leads_raw)

    return leads_list, total_count, total_pages, current_page, window_key


def _build_leads_pager_markup(page: int, total_pages: int, window: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    nav_row: list[InlineKeyboardButton] = []

    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"leads_page:{page - 1}:{window}",
            )
        )

    if total_pages and page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text="▶️ Далее",
                callback_data=f"leads_page:{page + 1}:{window}",
            )
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=f"leads_page:{page}:{window}",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_leads_pager_text(page: int, total_pages: int, total_count: int, window: str) -> str:
    label = _LEADS_WINDOW_LABELS.get(window, _LEADS_WINDOW_LABELS[DEFAULT_LEADS_WINDOW])
    return (
        f"Лиды: страница {page} из {total_pages}"
        f" • Всего: {total_count}"
        f" • Фильтр: {label}"
    )


async def _send_lead_cards(message: Message, leads: list[Any]) -> None:
    if not message:
        return

    for lead in leads:
        payload = {
            "tg_id": getattr(lead, "tg_id", None),
            "username": getattr(lead, "username", None),
            "first_name": getattr(lead, "first_name", None),
            "goal": getattr(lead, "goal", None),
            "calories": getattr(lead, "calories", None),
        }

        try:
            text, markup = build_lead_card(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to build lead card for %s: %s", payload.get("tg_id"), exc)
            continue

        try:
            await message.answer(text, parse_mode="HTML", reply_markup=markup)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send lead card for %s: %s", payload.get("tg_id"), exc)
            continue

        await asyncio.sleep(0.05)


async def _handle_all_leads_request(message: Message, page: int, window: str) -> None:
    try:
        leads, total_count, total_pages, current_page, window_key = await _load_leads_page(page, window)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load leads list: %s", exc)
        await message.answer("Не удалось загрузить список.")
        return

    if total_count <= 0 or not leads:
        await message.answer("Список пуст.")
        return

    await _send_lead_cards(message, leads)

    pager_text = _format_leads_pager_text(current_page, total_pages, total_count, window_key)
    pager_markup = _build_leads_pager_markup(current_page, total_pages, window_key)

    try:
        await message.answer(pager_text, reply_markup=pager_markup)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send leads pager: %s", exc)


# ---------------------------
# Хэндлеры
# ---------------------------

@user.message(Command("all_leads"))
@rate_limit
@error_handler
async def cmd_all_leads(message: Message, command: CommandObject) -> None:
    """Отобразить список лидов для администратора."""

    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page, window = _parse_leads_command_args(args)

    await _handle_all_leads_request(message, page, window)


@user.message(Command("all_leads_today"))
@rate_limit
@error_handler
async def cmd_all_leads_today(message: Message, command: CommandObject) -> None:
    """Отобразить лиды за последние 24 часа."""

    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page = _parse_page_arg(args)

    await _handle_all_leads_request(message, page, "today")


@user.message(Command("all_leads_7d"))
@rate_limit
@error_handler
async def cmd_all_leads_7d(message: Message, command: CommandObject) -> None:
    """Отобразить лиды за последние 7 дней."""

    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page = _parse_page_arg(args)

    await _handle_all_leads_request(message, page, "7d")


@user.callback_query(F.data.startswith("leads_page:"))
@rate_limit
@error_handler
async def paginate_leads(callback: CallbackQuery) -> None:
    """Навигация по страницам лидов."""

    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = callback.data or ""
    parts = data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    try:
        requested_page = int(parts[1])
    except ValueError:
        requested_page = 1

    window = parts[2]

    try:
        leads, total_count, total_pages, current_page, window_key = await _load_leads_page(requested_page, window)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to paginate leads: %s", exc)
        if callback.message:
            try:
                await callback.message.edit_text("Не удалось загрузить список.", reply_markup=None)
            except Exception as edit_exc:  # noqa: BLE001
                logger.warning("Failed to update pager message after error: %s", edit_exc)
        await callback.answer("Ошибка загрузки", show_alert=True)
        return

    if total_count <= 0 or not leads:
        if callback.message:
            try:
                await callback.message.edit_text("Список пуст.", reply_markup=None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to update pager message for empty list: %s", exc)
        await callback.answer()
        return

    if callback.message:
        try:
            await callback.message.edit_text(
                _format_leads_pager_text(current_page, total_pages, total_count, window_key),
                reply_markup=_build_leads_pager_markup(current_page, total_pages, window_key),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to edit leads pager message: %s", exc)

        await _send_lead_cards(callback.message, leads)
    else:
        logger.warning("Callback without message for leads pagination")

    await callback.answer()


def _parse_tg_id_from_callback(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None

    try:
        tg_id_value = int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None

    return tg_id_value


def _build_lead_delete_confirmation_markup(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да",
                    callback_data=f"lead_delete_confirm:{tg_id}",
                ),
                InlineKeyboardButton(
                    text="✖️ Нет",
                    callback_data="lead_delete_cancel",
                ),
            ]
        ]
    )


@user.callback_query(F.data.startswith("lead_delete:"))
@rate_limit
@error_handler
async def lead_delete_request(callback: CallbackQuery) -> None:
    """Показать подтверждение удаления лида."""

    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to initiate lead deletion", callback.from_user.id
        )
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = callback.data or ""
    tg_id = _parse_tg_id_from_callback(data, "lead_delete:")
    if tg_id is None:
        logger.error("Failed to parse lead deletion request from data: %s", data)
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    if not callback.message:
        logger.warning("Lead delete request without message for tg_id %s", tg_id)
        await callback.answer("Нет сообщения", show_alert=True)
        return

    confirmation_text = (
        "Вы уверены, что хотите удалить лида "
        f"<code>{tg_id}</code>?"
    )

    try:
        await callback.message.reply(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=_build_lead_delete_confirmation_markup(tg_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send lead delete confirmation for %s: %s", tg_id, exc)
        await callback.answer("Не удалось", show_alert=True)
        return

    await callback.answer()


@user.callback_query(F.data == "lead_delete_cancel")
@rate_limit
@error_handler
async def lead_delete_cancel(callback: CallbackQuery) -> None:
    """Отменить удаление лида."""

    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to cancel lead deletion", callback.from_user.id
        )
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    if callback.message:
        try:
            await callback.message.delete()
        except TelegramBadRequest as exc:
            logger.warning("Failed to delete lead delete confirmation message: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error when deleting confirmation message: %s", exc)

    await callback.answer("Отменено")


@user.callback_query(F.data.startswith("lead_delete_confirm:"))
@rate_limit
@error_handler
async def lead_delete_confirm(callback: CallbackQuery) -> None:
    """Удалить лида после подтверждения."""

    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to confirm lead deletion", callback.from_user.id
        )
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = callback.data or ""
    tg_id = _parse_tg_id_from_callback(data, "lead_delete_confirm:")
    if tg_id is None:
        logger.error("Failed to parse lead deletion confirmation from data: %s", data)
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    deletion_result = await safe_db_operation(delete_user_by_tg_id, tg_id)

    if not deletion_result:
        logger.warning("Lead deletion failed for tg_id %s", tg_id)
        if callback.message:
            try:
                await callback.message.edit_text(
                    "⚠️ Не удалось удалить лида. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to update confirmation message after error: %s", exc)
        await callback.answer("Не удалось", show_alert=True)
        return

    if callback.message:
        success_text = (
            f"✅ Лид <code>{tg_id}</code> удалён.\n"
            "Если карточка всё ещё отображается, нажмите «🔄 Обновить»."
        )
        try:
            await callback.message.edit_text(
                success_text,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to edit confirmation message after deletion: %s", exc)

        original_message = callback.message.reply_to_message
        if original_message:
            try:
                await original_message.delete()
            except TelegramBadRequest as exc:
                logger.warning("Failed to delete original lead card message: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error when deleting lead card message: %s", exc)

    await callback.answer("Удалено")


@user.message(CommandStart(), F.chat.type == "private")
@rate_limit
@error_handler
@track_user_activity("cmd_start")
async def cmd_start(message: Message):
    """Команда /start — создаём пользователя (если нужно) и показываем приветствие."""
    logger.debug("/start entered for user %s in chat %s", message.from_user.id if message.from_user else "unknown", message.chat.id if message.chat else "unknown")
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


@user.message(Command("ping"), F.chat.type == "private")
@rate_limit
@error_handler
async def cmd_ping(message: Message):
    """Быстрая проверка доступности бота."""
    logger.debug("/ping entered for user %s", message.from_user.id if message.from_user else "unknown")
    await message.answer("pong")


@user.message(Command("contact_author"), F.chat.type == "private")
@rate_limit
@error_handler
async def cmd_contact_author(message: Message) -> None:
    """Информация о том, как связаться с автором бота."""

    logger.debug(
        "/contact_author entered for user %s",
        message.from_user.id if message.from_user else "unknown",
    )
    await message.answer(get_text("contact_author"))


@user.callback_query(F.data == "main_menu")
@rate_limit
@error_handler
async def show_main_menu(callback: CallbackQuery):
    if not (callback.from_user and callback.message):
        return
    await callback.message.edit_text(get_text("main_menu"), reply_markup=main_menu(), parse_mode="HTML")
    await callback.answer()


@user.callback_query(F.data == "profile")
@rate_limit
@error_handler
async def show_profile(callback: CallbackQuery):
    """Профиль пользователя (если есть рассчитанные КБЖУ)."""
    if not (callback.from_user and callback.message):
        return

    user_data = await safe_db_operation(get_user, callback.from_user.id)
    if not user_data or not user_data.calories:
        await callback.message.edit_text(get_text("profile.no_data"), reply_markup=main_menu(), parse_mode="HTML")
        await callback.answer()
        return

    # текстовые подписи
    try:
        goal_text = get_text(f"goal_descriptions.{user_data.goal or 'maintenance'}")
        # пока используем helper; при переносе в JSON можно заменить на get_text("activity_labels.xxx")
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
                gender_icon=("👨" if user_data.gender == "male" else "👩"),
                gender_text=("Мужской" if user_data.gender == "male" else "Женский"),
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
        await callback.message.edit_text(get_text("errors.profile_error"), reply_markup=main_menu(), parse_mode="HTML")
        await callback.answer()


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


@user.callback_query(F.data == "start_kbju")
@rate_limit
@error_handler
@track_user_activity("start_kbju_flow")
async def start_kbju_flow(callback: CallbackQuery, state: FSMContext):
    """Старт сценария расчёта КБЖУ."""
    if not (callback.from_user and callback.message):
        return

    await _start_kbju_flow_inner(callback)
    await callback.answer()


@user.callback_query(F.data == CHECK_CALLBACK_DATA)
@rate_limit
@error_handler
async def subscription_gate_check(callback: CallbackQuery, state: FSMContext):
    if not (callback.from_user and callback.message):
        return

    await ensure_subscription_and_continue(
        callback.bot,
        callback.from_user.id,
        callback,
        on_success=lambda: _start_kbju_flow_inner(callback),
    )


@user.callback_query(F.data == "resume_calc")
@rate_limit
@error_handler
@track_user_activity("resume_calculation")
async def resume_calculation(callback: CallbackQuery, state: FSMContext):
    """Обработчик напоминания для продолжения расчёта."""
    if not (callback.from_user and callback.message):
        return

    user_id = callback.from_user.id
    await _cancel_stalled_reminder(user_id)
    await state.clear()
    await _start_kbju_flow_inner(callback)
    await callback.answer()


@user.callback_query(F.data.startswith("gender_"))
@rate_limit
@error_handler
@track_user_activity("process_gender")
async def process_gender(callback: CallbackQuery, state: FSMContext):
    if not (callback.from_user and callback.message and callback.data):
        return

    try:
        gender = callback.data.split("_", 1)[1]  # male/female
        if gender not in {"male", "female"}:
            return

        persist_result = await safe_db_operation(
            update_user_data,
            callback.from_user.id,
            gender=gender,
        )
        if persist_result is False:
            logger.warning(
                "Failed to persist gender for user %s", callback.from_user.id
            )

        await state.update_data(gender=gender)

        await callback.message.edit_text(get_text("questions.age"), parse_mode="HTML")
        await state.set_state(KBJUStates.waiting_age)
        await _restart_stalled_reminder(callback.from_user.id)
        await callback.answer()
    except Exception as e:
        logger.exception("Gender processing error: %s", e)
        await callback.answer("Ошибка обработки данных")


@user.message(KBJUStates.waiting_age)
@rate_limit
@error_handler
@track_user_activity("process_age")
async def process_age(message: Message, state: FSMContext):
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        age = int(text)
        if VALIDATION_LIMITS["age"]["min"] <= age <= VALIDATION_LIMITS["age"]["max"]:
            await state.update_data(age=age)
            await message.answer(get_text("questions.weight", age=age), parse_mode="HTML")
            await state.set_state(KBJUStates.waiting_weight)
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.age_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.age_invalid"), parse_mode="HTML")


@user.message(KBJUStates.waiting_weight)
@rate_limit
@error_handler
@track_user_activity("process_weight")
async def process_weight(message: Message, state: FSMContext):
    if not (message.from_user and message.text):
        return

    text = sanitize_text(message.text.strip(), 10)
    try:
        weight = float(text.replace(",", "."))
        if VALIDATION_LIMITS["weight"]["min"] <= weight <= VALIDATION_LIMITS["weight"]["max"]:
            await state.update_data(weight=weight)
            await message.answer(get_text("questions.height", weight=weight), parse_mode="HTML")
            await state.set_state(KBJUStates.waiting_height)
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.weight_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.weight_invalid"), parse_mode="HTML")


@user.message(KBJUStates.waiting_height)
@rate_limit
@error_handler
@track_user_activity("process_height")
async def process_height(message: Message, state: FSMContext):
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
            await _restart_stalled_reminder(message.from_user.id)
        else:
            await message.answer(get_text("errors.height_range"), parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(get_text("errors.height_invalid"), parse_mode="HTML")


@user.callback_query(F.data.startswith("activity_"))
@rate_limit
@error_handler
@track_user_activity("process_activity")
async def process_activity(callback: CallbackQuery, state: FSMContext):
    if not (callback.from_user and callback.message and callback.data):
        return

    raw = callback.data.split("_", 1)[1]  # min/low/medium/high
    activity = ACTIVITY_INPUT_MAP.get(raw, "moderate")
    await state.update_data(activity=activity)

    activity_text = _activity_label_from_buttons(raw)  # берём подпись кнопки из JSON
    await callback.message.edit_text(
        get_text("questions.goal", activity_text=activity_text),
        reply_markup=goal_keyboard(),
        parse_mode="HTML",
    )
    await _restart_stalled_reminder(callback.from_user.id)
    await callback.answer()


@user.callback_query(F.data.startswith("goal_"))
@rate_limit
@error_handler
@track_user_activity("process_goal")
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Финал — считаем КБЖУ, показываем результат, ставим таймер, отправляем вебхук и отложенное предложение."""
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
        goal = callback.data.split("_", 1)[1]  # weight_loss/maintenance/weight_gain
        data = await state.get_data()
        data["goal"] = goal

        # Рассчитываем КБЖУ и сохраняем данные пользователя
        kbju = await calculate_and_save_kbju(callback.from_user.id, data)
        await _cancel_stalled_reminder(callback.from_user.id)

        # Запускаем таймер для воронки
        asyncio.create_task(start_funnel_timer(callback.from_user.id))
        
        # Показываем результаты пользователю
        await show_kbju_results(callback, kbju, goal)
        
        # ВАЖНО: Отправляем calculated lead в n8n
        user_data = await get_user(callback.from_user.id)
        if user_data:
            logger.info(f"[Webhook] Отправляем calculated lead: {user_data.tg_id}, статус: {user_data.funnel_status}")
            await WebhookService.send_calculated_lead(_user_to_dict(user_data))
        else:
            logger.warning(f"[Webhook] Не удалось получить данные пользователя {callback.from_user.id} для отправки calculated lead")
        
        # Планируем отложенное предложение
        schedule_delayed_offer(callback.from_user.id, callback.message.chat.id)
        
        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.exception("process_goal error: %s", e)
        try:
            await callback.message.edit_text(get_text("errors.calculation_error"), reply_markup=back_to_menu(), parse_mode="HTML")
            await state.clear()
        except Exception as e2:
            logger.exception("Failed to send error message: %s", e2)


@user.callback_query(F.data == "delayed_yes")
@rate_limit
@error_handler
@track_user_activity("process_delayed_yes")
async def process_delayed_yes(callback: CallbackQuery):
    """Пользователь готов — выбираем приоритет."""
    if not (callback.from_user and callback.message):
        return

    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception:
        pass
    await _cancel_stalled_reminder(callback.from_user.id)

    await callback.message.edit_text(get_text("hot_lead_priorities"), reply_markup=priority_keyboard(), parse_mode="HTML")
    await callback.answer()


@user.callback_query(F.data == "delayed_no")
@rate_limit
@error_handler
@track_user_activity("process_delayed_no")
async def process_delayed_no(callback: CallbackQuery):
    """Пользователь хочет советы — холодный лид (delayed)."""
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
        get_text("cold_lead_advice", advice_text=advice_text, channel_url=CHANNEL_URL or "@fitness_channel"),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data == "send_lead")
@rate_limit
@error_handler
@track_user_activity("process_lead_request")
async def process_lead_request(callback: CallbackQuery):
    """Оставить заявку (горячий лид)."""
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

    try:
        cancel_delayed_offer(callback.from_user.id)
    except Exception:
        logger.debug(
            "Failed to cancel delayed offer for user %s", callback.from_user.id, exc_info=True
        )

    updated_user = await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES["hotlead_consultation"],
        priority_score=PRIORITY_SCORES["consultation_request"],
    )

    user_record = updated_user or await get_user(callback.from_user.id) or user_before

    if user_record and not already_hot_lead:
        try:
            await WebhookService.send_hot_lead(
                _user_to_dict(user_record), "consultation_request"
            )
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
            username=callback.from_user.username or "не указан",
        ),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@user.callback_query(F.data.startswith("priority_"))
@rate_limit
@error_handler
@track_user_activity("process_priority")
async def process_priority(callback: CallbackQuery):
    """Выбор приоритета → оффер консультации."""
    if not (callback.from_user and callback.message and callback.data):
        return

    priority = callback.data.split("_", 1)[1]  # nutrition/training/schedule

    await update_user_data(
        tg_id=callback.from_user.id,
        priority=priority,
    )

    await callback.message.edit_text(get_text("consultation_offer"), reply_markup=consultation_contact_keyboard(), parse_mode="HTML")
    await callback.answer()


@user.callback_query(F.data == "funnel_cold")
@rate_limit
@error_handler
@track_user_activity("process_cold_lead")
async def process_cold_lead(callback: CallbackQuery):
    """Ручной переход в холодные лиды (получить советы)."""
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
        get_text("cold_lead_advice", advice_text=advice_text, channel_url=CHANNEL_URL or "@fitness_channel"),
        reply_markup=back_to_menu(),
        parse_mode="HTML",
    )
    await callback.answer()

import asyncio
import html
import logging
from typing import Any, Mapping, Optional, Tuple
import logging
from typing import Optional

import aiohttp
from aiohttp import ClientError, ClientTimeout

from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN

TELEGRAM_API_URL = "https://api.telegram.org"
CONTACT_REQUEST_MESSAGE = "Админ хочет с вами связаться, ответьте на это сообщение"

logger = logging.getLogger(__name__)

_GOAL_LABELS: Mapping[str, str] = {
    "weight_loss": "Похудение",
    "maintenance": "Поддержание",
    "weight_gain": "Набор массы",
}


def _value_from_user(user: Mapping[str, Any] | Any, key: str) -> Any:
    """Возвращает значение атрибута/ключа из произвольного объекта пользователя."""
    if isinstance(user, Mapping):
        return user.get(key)
    return getattr(user, key, None)


def _sanitize_username(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    return username.lstrip("@")


def _format_goal(goal: Optional[str]) -> str:
    if not goal:
        return "—"
    goal_key = str(goal)
    return _GOAL_LABELS.get(goal_key, goal_key)


def _format_calories(calories: Any) -> str:
    if calories in (None, ""):
        return "—"
    try:
        return f"{int(float(calories))}"
    except (TypeError, ValueError):
        return str(calories)


def build_lead_card(user: Mapping[str, Any] | Any) -> Tuple[str, dict]:
    """Сформировать текст и клавиатуру карточки лида для уведомления админу."""
    tg_id = _value_from_user(user, "tg_id")
    if tg_id is None:
        raise ValueError("tg_id is required to build lead card")

    try:
        tg_id_int = int(tg_id)
    except (TypeError, ValueError) as exc:  # noqa: BLE001 - логируем понятную ошибку
        raise ValueError(f"tg_id must be integer-compatible, got {tg_id!r}") from exc

    first_name = _value_from_user(user, "first_name")
    username_raw = _sanitize_username(_value_from_user(user, "username"))
    goal = _format_goal(_value_from_user(user, "goal"))
    calories = _format_calories(_value_from_user(user, "calories"))

    display_name = first_name or username_raw or f"ID {tg_id_int}"
    safe_name = html.escape(str(display_name))

    username_line = (
        f"💬 @{html.escape(username_raw)}\n" if username_raw else ""
    )

    mention_link = f'<a href="tg://user?id={tg_id_int}">Открыть профиль</a>'

    text = (
        "<b>Новый лид</b>\n"
        f"👤 {safe_name}\n"
        f"🆔 <code>{tg_id_int}</code>\n"
        f"🎯 Цель: {html.escape(goal)}\n"
        f"🔥 Калории: {html.escape(calories)}\n"
        f"{username_line}"
        f"{mention_link}"
    )

    if username_raw:
        profile_url = f"https://t.me/{username_raw}"
    else:
        profile_url = f"tg://user?id={tg_id_int}"

    reply_markup = {
        "inline_keyboard": [
            [{"text": "👤 Открыть профиль", "url": profile_url}],
            [
                {"text": "📨 Связаться", "callback_data": f"lead_contact:{tg_id_int}"},
                {"text": "📝 Написать от бота", "callback_data": f"lead_reply:{tg_id_int}"},
            ],
        ]
    }

    return text, reply_markup


async def send_telegram_message(
    message: str,
    *,
    chat_id: int = ADMIN_CHAT_ID,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict] = None,
) -> None:

logger = logging.getLogger(__name__)


async def send_telegram_message(message: str, chat_id: int = ADMIN_CHAT_ID) -> None:
    """Отправить сообщение через Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; skipping Telegram notification")
        return

    url = f"{TELEGRAM_API_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    payload = {"chat_id": chat_id, "text": message}

    try:
        timeout = ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    body: Optional[str] = None
                    try:
                        body = await response.text()
                    except Exception:  # noqa: BLE001 - логируем, но не прерываем
                        body = None
                    logger.error(
                        "Failed to send Telegram notification: status=%s, body=%s",
                        response.status,
                        body,
                    )
    except (ClientError, asyncio.TimeoutError) as exc:
        logger.error("Error sending Telegram notification: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while sending Telegram notification: %s", exc)

async def notify_new_lead(user: Mapping[str, Any] | Any) -> None:
    """Собрать карточку лида и отправить админу."""
    try:
        text, markup = build_lead_card(user)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build lead card: %s", exc)
        return

    await send_telegram_message(text, parse_mode="HTML", reply_markup=markup)
    
def format_lead_message(name: str, contact: str) -> str:
    """Сформировать текст уведомления о новом лиде."""
    safe_name = name or "Не указано"
    safe_contact = contact or "контакт не указан"
    return f"Новый лид: {safe_name}, {safe_contact}"


async def notify_new_lead(name: str, contact: str) -> None:
    """Отправить админу уведомление о новом лиде."""
    message = format_lead_message(name, contact)
    await send_telegram_message(message)

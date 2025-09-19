import asyncio
import logging
from typing import Optional

import aiohttp
from aiohttp import ClientError, ClientTimeout

from config import TELEGRAM_BOT_TOKEN

TELEGRAM_API_URL = "https://api.telegram.org"
ADMIN_CHAT_ID = 310151740

logger = logging.getLogger(__name__)


async def send_telegram_message(message: str, chat_id: int = ADMIN_CHAT_ID) -> None:
    """Отправить сообщение через Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; skipping Telegram notification")
        return

    url = f"{TELEGRAM_API_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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


def format_lead_message(name: str, contact: str) -> str:
    """Сформировать текст уведомления о новом лиде."""
    safe_name = name or "Не указано"
    safe_contact = contact or "контакт не указан"
    return f"Новый лид: {safe_name}, {safe_contact}"


async def notify_new_lead(name: str, contact: str) -> None:
    """Отправить админу уведомление о новом лиде."""
    message = format_lead_message(name, contact)
    await send_telegram_message(message)

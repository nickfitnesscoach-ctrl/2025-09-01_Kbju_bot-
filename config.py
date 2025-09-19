"""Конфигурационный файл для Fitness Bot."""

from __future__ import annotations

import logging
import os
from typing import Iterable

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

# Загружаем переменные из .env файла
load_dotenv()


def _bool(value: str) -> bool:
    """Конвертируем строку в boolean."""

    return str(value).lower() in ("1", "true", "yes", "y", "on")


def _int(value: str | None, *, field_name: str | None = None) -> int | None:
    """Безопасно конвертируем строку в int с логированием ошибок."""

    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        target = f" для {field_name}" if field_name else ""
        logger.warning("Invalid integer%s: %s", target, value)
        return None


def _first_non_empty(names: Iterable[str]) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


# Совместимость имён токена
TELEGRAM_BOT_TOKEN = _first_non_empty(("TELEGRAM_BOT_TOKEN", "TOKEN", "BOT_TOKEN"))
TOKEN = TELEGRAM_BOT_TOKEN
BOT_TOKEN = TELEGRAM_BOT_TOKEN

# Администратор
ADMIN_CHAT_ID = _int(os.getenv("ADMIN_CHAT_ID"), field_name="ADMIN_CHAT_ID")

# База данных
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///data/db.sqlite3")

# Webhook для интеграции с n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")

# URL канала
CHANNEL_URL = os.getenv("CHANNEL_URL", "")

# Режим отладки
DEBUG = _bool(os.getenv("DEBUG", "false"))
ENABLE_HOT_LEAD_ALERTS = os.getenv("ENABLE_HOT_LEAD_ALERTS", "true").lower() == "true"

# Напоминание пользователям, которые не завершили расчёт
STALLED_REMINDER_DELAY_MIN = int(os.getenv("STALLED_REMINDER_DELAY_MIN", "120"))

_missing_required: list[str] = []
if not TELEGRAM_BOT_TOKEN:
    _missing_required.append("TELEGRAM_BOT_TOKEN")


def validate_required_settings() -> None:
    """Проверить наличие обязательных переменных окружения."""

    if not _missing_required:
        return

    message = (
        "Missing required environment variables: "
        + ", ".join(_missing_required)
        + ". Please set them in your environment or .env file."
    )
    raise RuntimeError(message)


if ADMIN_CHAT_ID is None:
    logger.warning(
        "ADMIN_CHAT_ID is not configured; admin shortcuts and notifications will be limited"
    )

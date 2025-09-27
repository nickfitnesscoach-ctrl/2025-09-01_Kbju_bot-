"""Конфигурационный файл для Fitness Bot."""

from __future__ import annotations

import logging
import os
from typing import Iterable

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

# Загружаем переменные из .env файла
load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Конвертировать строку в булево значение с поддержкой дефолта."""

    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


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

# Проверка подписки на канал
ENABLE_SUBSCRIPTION_GATE = _as_bool(os.getenv("ENABLE_SUBSCRIPTION_GATE"), True)
CHANNEL_URL = os.getenv("CHANNEL_URL", "")
CHANNEL_ID_OR_USERNAME = os.getenv("CHANNEL_ID_OR_USERNAME", "")
ALLOW_GATE_FALLBACK_PASS = _as_bool(os.getenv("ALLOW_GATE_FALLBACK_PASS"), False)

# Режим отладки
DEBUG = _as_bool(os.getenv("DEBUG"), False)
ENABLE_HOT_LEAD_ALERTS = _as_bool(os.getenv("ENABLE_HOT_LEAD_ALERTS"), True)

# Напоминание пользователям, которые не завершили расчёт
ENABLE_STALLED_REMINDER = _as_bool(os.getenv("ENABLE_STALLED_REMINDER"), False)
STALLED_REMINDER_DELAY_MIN = int(os.getenv("STALLED_REMINDER_DELAY_MIN", "120"))

# Догоняющие кейсы по неактивности
ENABLE_DRIP_FOLLOWUPS = _as_bool(os.getenv("ENABLE_DRIP_FOLLOWUPS"), False)

_DRIP_INTERVAL = _int(
    os.getenv("DRIP_CHECK_INTERVAL_SEC"), field_name="DRIP_CHECK_INTERVAL_SEC"
)
DRIP_CHECK_INTERVAL_SEC = _DRIP_INTERVAL if _DRIP_INTERVAL is not None else 600

_DRIP_STAGE_1 = _int(os.getenv("DRIP_STAGE_1_MIN"), field_name="DRIP_STAGE_1_MIN")
DRIP_STAGE_1_MIN = _DRIP_STAGE_1 if _DRIP_STAGE_1 is not None else 60

_DRIP_STAGE_2 = _int(os.getenv("DRIP_STAGE_2_MIN"), field_name="DRIP_STAGE_2_MIN")
DRIP_STAGE_2_MIN = _DRIP_STAGE_2 if _DRIP_STAGE_2 is not None else 1_440

_DRIP_STAGE_3 = _int(os.getenv("DRIP_STAGE_3_MIN"), field_name="DRIP_STAGE_3_MIN")
DRIP_STAGE_3_MIN = _DRIP_STAGE_3 if _DRIP_STAGE_3 is not None else 2_880

_DRIP_STAGE_4 = _int(os.getenv("DRIP_STAGE_4_MIN"), field_name="DRIP_STAGE_4_MIN")
if _DRIP_STAGE_4 is not None:
    DRIP_STAGE_4_MIN = _DRIP_STAGE_4
else:
    DRIP_STAGE_4_MIN = DRIP_STAGE_3_MIN + 1_440

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


def log_drip_configuration(
    target_logger: logging.Logger | None = None,
    *,
    worker_running: bool | None = None,
) -> None:
    """Вывести в лог настройки догоняющих кейсов."""

    active_logger = target_logger or logger
    worker_state = (
        "running" if worker_running else "stopped"
        if worker_running is not None
        else "unknown"
    )

    active_logger.info(
        "DRIP: enabled=%s | pid=%s | worker_state=%s | interval_sec=%s | "
        "thresholds_min=(stage1=%s, stage2=%s, stage3=%s, stage4=%s)",
        ENABLE_DRIP_FOLLOWUPS,
        os.getpid(),
        worker_state,
        DRIP_CHECK_INTERVAL_SEC,
        DRIP_STAGE_1_MIN,
        DRIP_STAGE_2_MIN,
        DRIP_STAGE_3_MIN,
        DRIP_STAGE_4_MIN,
    )


if ADMIN_CHAT_ID is None:
    logger.warning(
        "ADMIN_CHAT_ID is not configured; admin shortcuts and notifications will be limited"
    )

"""
Конфигурационный файл для Fitness Bot
Загружает настройки из переменных окружения
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

def _bool(value: str) -> bool:
    """Конвертируем строку в boolean"""
    return str(value).lower() in ("1", "true", "yes", "y", "on")

# Совместимость имён токена
TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TOKEN")
    or os.getenv("BOT_TOKEN", "")
)
TOKEN = TELEGRAM_BOT_TOKEN
BOT_TOKEN = TELEGRAM_BOT_TOKEN

# Администратор
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "310151740"))

# База данных
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///data/db.sqlite3")

# Webhook для интеграции с n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")

# URL канала
CHANNEL_URL = os.getenv("CHANNEL_URL", "")

# Режим отладки
DEBUG = _bool(os.getenv("DEBUG", "false"))

# Проверка обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    print("⚠️ ВНИМАНИЕ: BOT_TOKEN не установлен!")
    print("Создайте .env файл и укажите BOT_TOKEN=your_bot_token_here")

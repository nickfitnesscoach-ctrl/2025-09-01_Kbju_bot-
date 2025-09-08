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
TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN", "")
BOT_TOKEN = TOKEN

# База данных
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///data/db.sqlite3")

# Webhook для интеграции с n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# URL канала
CHANNEL_URL = os.getenv("CHANNEL_URL", "")

# Режим отладки
DEBUG = _bool(os.getenv("DEBUG", "false"))

# Проверка обязательных переменных
if not TOKEN:
    print("⚠️ ВНИМАНИЕ: BOT_TOKEN не установлен!")
    print("Создайте .env файл и укажите BOT_TOKEN=your_bot_token_here")
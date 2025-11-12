"""
Скрипт для инициализации дефолтных настроек в БД
Использование: python scripts/init_default_settings.py
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database.requests import set_setting
from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED, DEFAULT_OFFER_TEXT


async def init_settings():
    """Установить дефолтные настройки"""
    
    print("🔧 Инициализация дефолтных настроек бота...")
    
    # Дефолтный текст оффера
    await set_setting(SETTING_OFFER_TEXT, DEFAULT_OFFER_TEXT)
    print(f"✅ Установлено: {SETTING_OFFER_TEXT}")
    
    # Drip включена по умолчанию
    await set_setting(SETTING_DRIP_ENABLED, "true")
    print(f"✅ Установлено: {SETTING_DRIP_ENABLED} = true")
    
    print("\n✅ Дефолтные настройки успешно инициализированы!")


if __name__ == '__main__':
    try:
        asyncio.run(init_settings())
    except Exception as exc:
        print(f"\n❌ Ошибка при инициализации настроек: {exc}")
        sys.exit(1)

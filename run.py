import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.admin import admin
from app.database.models import async_main
from app.user import user
from config import DEBUG, N8N_WEBHOOK_URL, TOKEN


async def main():
    """Основная функция запуска бота"""
    
    # Настройка логирования
    if DEBUG:
        logging.basicConfig(level=logging.INFO)
        print("[DEBUG] Fitness Bot starting in debug mode")
    else:
        logging.basicConfig(level=logging.WARNING)
        print("[PROD] Fitness Bot starting in production mode")
    
    # Создание бота с HTML разметкой по умолчанию
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создание диспетчера с FSM хранилищем
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключение роутеров
    dp.include_routers(user, admin)
    
    # Регистрация событий
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    
    # Запуск поллинга
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


async def startup(dispatcher: Dispatcher):
    """Функция запуска - инициализация БД и проверка настроек"""
    try:
        # Создание таблиц БД
        await async_main()
        print("[OK] Database initialized")
        
        # Проверка настроек
        if N8N_WEBHOOK_URL:
            print(f"[OK] N8N Webhook configured: {N8N_WEBHOOK_URL[:50]}...")
            
            # Тестирование соединения с webhook
            if DEBUG:
                from app.webhook import test_webhook_connection
                webhook_ok = await test_webhook_connection()
                if webhook_ok:
                    print("[OK] Webhook connection works")
                else:
                    print("[WARN] Webhook connection issues")
        else:
            print("[WARN] N8N Webhook not configured - integration disabled")
        
        print("[SUCCESS] Fitness Bot started successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"[ERROR] Startup failed: {e}")
        raise


async def shutdown(dispatcher: Dispatcher):
    """Функция остановки бота"""
    print("[INFO] Stopping Fitness Bot...")
    
    # Отменяем все активные таймеры
    try:
        from app.webhook import TimerService
        for user_id in list(TimerService.active_timers.keys()):
            TimerService.cancel_timer(user_id)
        print("[OK] All timers cancelled")
    except Exception as e:
        print(f"[WARN] Timer cancellation error: {e}")
    
    print("[INFO] Fitness Bot stopped")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Received shutdown signal")
    except Exception as e:
        print(f"[CRITICAL] Fatal error: {e}")

import asyncio
import logging
from typing import Iterable

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from app.admin import admin
from app.database.models import async_main
from app.drip_followups import DripFollowupService
from app.user import user
from config import (
    ADMIN_CHAT_ID,
    DEBUG,
    ENABLE_HOT_LEAD_ALERTS,
    ENABLE_STALLED_REMINDER,
    N8N_WEBHOOK_URL,
    STALLED_REMINDER_DELAY_MIN,
    TOKEN,
    validate_required_settings,
    log_drip_configuration,
)

logger = logging.getLogger(__name__)

ALLOWED_UPDATES: tuple[str, ...] = ("message", "callback_query", "my_chat_member")
POLLING_MODE = "polling"


def _mask_admin_chat_id(admin_id: int | None) -> str:
    if admin_id is None:
        return "not-set"

    admin_str = str(admin_id)
    if len(admin_str) <= 2:
        return "*" * len(admin_str)
    return f"{'*' * (len(admin_str) - 2)}{admin_str[-2:]}"


def _log_startup_configuration(allowed_updates: Iterable[str]) -> None:
    masked_admin = _mask_admin_chat_id(ADMIN_CHAT_ID)
    logger.info(
        "Startup configuration | ENABLE_HOT_LEAD_ALERTS=%s | ADMIN_CHAT_ID=%s | "
        "mode=%s | allowed_updates=%s",
        ENABLE_HOT_LEAD_ALERTS,
        masked_admin,
        POLLING_MODE,
        list(allowed_updates),
    )
    logger.info(
        "STALLED: enabled=%s delay_min=%s",
        ENABLE_STALLED_REMINDER,
        STALLED_REMINDER_DELAY_MIN,
    )
    log_drip_configuration(logger, worker_running=DripFollowupService.is_running())


async def _configure_bot_commands(bot: Bot) -> None:
    private_commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="contact_author", description="Связь с автором"),
    ]

    try:
        await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
        logger.debug("Private chat commands configured: %s", [cmd.command for cmd in private_commands])
    except Exception as exc:  # noqa: BLE001 - логируем, но не прерываем запуск
        logger.warning("Failed to configure private commands: %s", exc)

    if ADMIN_CHAT_ID is None:
        return

    admin_commands = private_commands + [
        BotCommand(command="admin", description="Админ-меню"),
    ]

    try:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_CHAT_ID))
        logger.debug("Admin commands configured for chat %s", _mask_admin_chat_id(ADMIN_CHAT_ID))
    except Exception as exc:  # noqa: BLE001 - предупреждаем, но не падаем
        logger.warning("Failed to configure admin commands: %s", exc)


async def main():
    """Основная функция запуска бота"""
    
    # Настройка логирования
    log_level = logging.DEBUG if DEBUG else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.getLogger("aiogram").setLevel(log_level)
    logging.getLogger("aiogram.event").setLevel(log_level)
    logger.debug("Fitness Bot starting in debug mode") if DEBUG else logger.info(
        "Fitness Bot starting in production mode"
    )
    
    try:
        validate_required_settings()
    except RuntimeError as err:
        logging.critical("%s", err)
        raise SystemExit(1) from err

    # Создание бота с HTML разметкой по умолчанию
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создание диспетчера с FSM хранилищем
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключение роутеров
    dp.include_routers(user, admin)

    _log_startup_configuration(ALLOWED_UPDATES)

    # Регистрация событий
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)

    # Запуск поллинга
    try:
        await dp.start_polling(bot, allowed_updates=list(ALLOWED_UPDATES))
    finally:
        await bot.session.close()


async def startup(dispatcher: Dispatcher, bot: Bot):
    """Функция запуска - инициализация БД и проверка настроек"""
    try:
        # Создание таблиц БД
        await async_main()
        logger.info("Database initialized")

        # Проверка настроек
        if N8N_WEBHOOK_URL:
            logger.info("N8N Webhook configured: %s...", N8N_WEBHOOK_URL[:50])

            # Тестирование соединения с webhook
            if DEBUG:
                from app.webhook import test_webhook_connection
                webhook_ok = await test_webhook_connection()
                if webhook_ok:
                    logger.info("Webhook connection works")
                else:
                    logger.warning("Webhook connection issues")
        else:
            logger.warning("N8N Webhook not configured - integration disabled")

        await _configure_bot_commands(bot)

        logger.info("Fitness Bot started successfully!")
        logger.info("%s", "=" * 50)

        DripFollowupService.start(bot)

    except Exception as e:
        logger.exception("Startup failed: %s", e)
        raise


async def shutdown(dispatcher: Dispatcher):
    """Функция остановки бота"""
    logger.info("Stopping Fitness Bot...")

    try:
        await DripFollowupService.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to stop drip follow-up worker: %s", exc)

    # Отменяем все активные таймеры
    try:
        from app.webhook import TimerService
        for user_id in list(TimerService.active_timers.keys()):
            TimerService.cancel_timer(user_id)
        logger.info("All timers cancelled")
    except Exception as e:
        logger.warning("Timer cancellation error: %s", e)

    logger.info("Fitness Bot stopped")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.critical("Fatal error: %s", e)

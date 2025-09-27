"""General user-facing commands and callbacks."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, URLInputFile
from sqlalchemy import select

from app.database.models import User, async_session

from app.calculator import get_activity_description
from app.database.requests import get_user, upsert_user
from app.keyboards import main_menu, profile_keyboard
from app.texts import get_media_id, get_text
from utils.notifications import notify_lead_card

from .shared import error_handler, rate_limit, safe_db, safe_db_operation, sanitize_text, track_user_activity

logger = logging.getLogger(__name__)


def register(router: Router) -> None:
    router.message.register(cmd_start, CommandStart(), F.chat.type == ChatType.PRIVATE)
    router.message.register(cmd_ping, Command("ping"), F.chat.type == ChatType.PRIVATE)
    router.message.register(
        cmd_contact_author,
        Command("contact_author"),
        F.chat.type == ChatType.PRIVATE,
    )
    router.callback_query.register(show_main_menu, F.data == "main_menu")
    router.callback_query.register(show_profile, F.data == "profile")


async def send_welcome_sequence(message: Message) -> None:
    photo_sent = False
    file_id = get_media_id("coach_photo_file_id")
    if file_id:
        logger.debug("Sending welcome photo via file_id")
        try:
            await message.answer_photo(file_id)
            photo_sent = True
        except Exception as exc:  # noqa: BLE001 - continue with fallback logic
            logger.warning("Welcome photo via file_id failed: %s", exc)
    else:
        logger.debug("No cached file_id for welcome photo")

    if not photo_sent:
        photo_url = get_text("coach_photo_url")
        if photo_url:
            try:
                logger.debug("Sending welcome photo via URL")
                await message.answer_photo(URLInputFile(photo_url))
                photo_sent = True
            except Exception as exc:  # noqa: BLE001 - fallback to text only welcome
                logger.warning("Welcome photo via URL failed: %s", exc)

    try:
        await message.answer(get_text("welcome"), reply_markup=main_menu(), parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(get_text("fallbacks.welcome_plain"), reply_markup=main_menu())


@rate_limit
@error_handler
@track_user_activity("cmd_start")
async def cmd_start(message: Message) -> None:
    """Create or update a lead and show the welcome sequence."""

    if not message.from_user or not message.from_user.id:
        logger.warning("Start without user info")
        return

    logger.debug(
        "/start entered for user %s in chat %s",
        message.from_user.id,
        message.chat.id if message.chat else "unknown",
    )

    username = sanitize_text(message.from_user.username or "", 50)
    first_name = sanitize_text(message.from_user.first_name or get_text("fallbacks.default_first_name"), 50)

    new_lead_payload: dict[str, Any] | None = None
    async with async_session() as session:
        existing_user_id = await session.scalar(
            select(User.id).where(User.tg_id == message.from_user.id)
        )
        is_new_user = existing_user_id is None

        try:
            await safe_db(
                upsert_user,
                session,
                tg_id=message.from_user.id,
                username=username or None,
                first_name=first_name or None,
            )
        except Exception as exc:  # noqa: BLE001 - мягкий ответ только на неожиданные исключения
            logger.exception("Failed to upsert user %s: %s", message.from_user.id, exc)
            await message.answer(get_text("errors.temp_error"), parse_mode="HTML")
            return

        if is_new_user:
            new_lead_payload = {
                "tg_id": message.from_user.id,
                "username": username,
                "first_name": first_name,
                "goal": None,
                "calories": None,
            }

    if new_lead_payload is not None:
        try:
            await notify_lead_card(new_lead_payload, title=get_text("admin.leads.new_title"))
        except Exception as exc:  # noqa: BLE001 - уведомление не должно ломать сценарий
            logger.exception(
                "Failed to send activation notification for user %s: %s",
                message.from_user.id,
                exc,
            )

    await send_welcome_sequence(message)


@rate_limit
@error_handler
async def cmd_ping(message: Message) -> None:
    logger.debug("/ping entered for user %s", message.from_user.id if message.from_user else "unknown")
    await message.answer(get_text("debug.ping_response"))


@rate_limit
@error_handler
async def cmd_contact_author(message: Message) -> None:
    logger.debug(
        "/contact_author entered for user %s",
        message.from_user.id if message.from_user else "unknown",
    )
    await message.answer(get_text("contact_author"))


@rate_limit
@error_handler
async def show_main_menu(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    await callback.message.edit_text(
        get_text("main_menu"),
        reply_markup=main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@rate_limit
@error_handler
async def show_profile(callback: CallbackQuery) -> None:
    if not (callback.from_user and callback.message):
        return

    user_data = await safe_db_operation(get_user, callback.from_user.id)
    if not user_data or not user_data.calories:
        await callback.message.edit_text(
            get_text("profile.no_data"),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    try:
        goal_text = get_text(f"goal_descriptions.{user_data.goal or 'maintenance'}")
        activity_text = get_activity_description(user_data.activity or "moderate")

        calc_date = get_text("profile.not_specified")
        if user_data.calculated_at:
            try:
                calc_date = user_data.calculated_at.strftime(get_text("profile.date_format"))
            except Exception:  # noqa: BLE001 - fallback to default label
                calc_date = get_text("profile.not_specified")

        gender_is_male = user_data.gender == "male"

        await callback.message.edit_text(
            get_text(
                "profile.template",
                gender_icon=get_text("profile.gender_male_icon") if gender_is_male else get_text("profile.gender_female_icon"),
                gender_text=get_text("profile.gender_male") if gender_is_male else get_text("profile.gender_female"),
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
    except Exception as exc:  # noqa: BLE001 - do not block the user
        logger.exception("Profile formatting error: %s", exc)
        await callback.message.edit_text(
            get_text("errors.profile_error"),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()

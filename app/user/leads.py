"""Admin lead management commands exposed inside the bot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.constants import LEADS_DEFAULT_WINDOW, LEADS_PAGE_SIZE
from app.database.requests import (
    count_started_leads,
    delete_user_by_tg_id,
    get_started_leads,
)
from app.texts import get_button_text, get_text
from config import ADMIN_CHAT_ID
from utils.notifications import build_lead_card

from .shared import error_handler, rate_limit, safe_db_operation

logger = logging.getLogger(__name__)


DEFAULT_LEADS_WINDOW = LEADS_DEFAULT_WINDOW


_LEADS_WINDOW_DELTAS: dict[str, timedelta | None] = {
    "all": None,
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
}


_LEADS_WINDOW_LABELS: dict[str, str] = {
    "all": get_text("admin.leads.pager_window_all"),
    "today": get_text("admin.leads.pager_window_today"),
    "7d": get_text("admin.leads.pager_window_7d"),
}


BUTTON_REFRESH = "leads_refresh"
BUTTON_CONFIRM_YES = "confirm_yes"
BUTTON_CONFIRM_NO = "confirm_no"


def register(router: Router) -> None:
    router.message.register(cmd_all_leads, Command("all_leads"))
    router.message.register(cmd_all_leads_today, Command("all_leads_today"))
    router.message.register(cmd_all_leads_7d, Command("all_leads_7d"))
    router.callback_query.register(paginate_leads, F.data.startswith("leads_page:"))
    router.callback_query.register(lead_delete_request, F.data.startswith("lead_delete:"))
    router.callback_query.register(lead_delete_cancel, F.data == "lead_delete_cancel")
    router.callback_query.register(lead_delete_confirm, F.data.startswith("lead_delete_confirm:"))


def _is_admin(user_id: int | None) -> bool:
    return bool(user_id and ADMIN_CHAT_ID and user_id == ADMIN_CHAT_ID)


async def _ensure_admin_access(message: Message) -> bool:
    if not message.from_user:
        return False
    if not _is_admin(message.from_user.id):
        await message.answer(get_text("admin.leads.no_permission"))
        return False
    return True


def _normalize_leads_window(window: str | None) -> str:
    if not window:
        return DEFAULT_LEADS_WINDOW
    window_key = window.lower()
    if window_key not in _LEADS_WINDOW_DELTAS:
        return DEFAULT_LEADS_WINDOW
    return window_key


def _parse_leads_command_args(args: str | None) -> tuple[int, str]:
    page = 1
    window = DEFAULT_LEADS_WINDOW
    if not args:
        return page, window

    for token in args.split():
        token = token.strip()
        if not token:
            continue

        token_lower = token.lower()
        if token_lower in _LEADS_WINDOW_DELTAS:
            window = token_lower
            continue

        try:
            page_value = int(token)
        except ValueError:
            continue

        if page_value > 0:
            page = page_value

    return page, window


def _parse_page_arg(args: str | None) -> int:
    if not args:
        return 1
    for token in args.split():
        token = token.strip()
        if not token:
            continue
        try:
            page_value = int(token)
        except ValueError:
            continue
        if page_value > 0:
            return page_value
    return 1


def _get_since_for_window(window: str) -> datetime | None:
    delta = _LEADS_WINDOW_DELTAS.get(window)
    if not delta:
        return None
    return datetime.utcnow() - delta


async def _load_leads_page(page: int, window: str) -> tuple[list[Any], int, int, int, str]:
    window_key = _normalize_leads_window(window)
    since = _get_since_for_window(window_key)

    count_raw = await safe_db_operation(count_started_leads, since=since)
    if count_raw in (False, None):
        raise RuntimeError("Failed to count started leads")

    total_count = int(count_raw)
    if total_count <= 0:
        return [], 0, 0, 1, window_key

    total_pages = (total_count + LEADS_PAGE_SIZE - 1) // LEADS_PAGE_SIZE
    current_page = page if page > 0 else 1
    if current_page > total_pages:
        current_page = total_pages

    offset = (current_page - 1) * LEADS_PAGE_SIZE

    leads_raw = await safe_db_operation(
        get_started_leads,
        offset=offset,
        limit=LEADS_PAGE_SIZE,
        since=since,
    )

    if leads_raw in (False, None):
        raise RuntimeError("Failed to load started leads")

    return list(leads_raw), total_count, total_pages, current_page, window_key


def _build_leads_pager_markup(page: int, total_pages: int, window: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    nav_row: list[InlineKeyboardButton] = []

    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=get_button_text("nav_prev"),
                callback_data=f"leads_page:{page - 1}:{window}",
            )
        )

    if total_pages and page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text=get_button_text("nav_next"),
                callback_data=f"leads_page:{page + 1}:{window}",
            )
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append(
        [
            InlineKeyboardButton(
                text=get_button_text(BUTTON_REFRESH),
                callback_data=f"leads_page:{page}:{window}",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_leads_pager_text(page: int, total_pages: int, total_count: int, window: str) -> str:
    label = _LEADS_WINDOW_LABELS.get(window, _LEADS_WINDOW_LABELS[DEFAULT_LEADS_WINDOW])
    return get_text(
        "admin.leads.pager_label",
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        window_label=label,
    )


async def _send_lead_cards(message: Message, leads: list[Any]) -> None:
    for lead in leads:
        payload = {
            "tg_id": getattr(lead, "tg_id", None),
            "username": getattr(lead, "username", None),
            "first_name": getattr(lead, "first_name", None),
            "goal": getattr(lead, "goal", None),
            "calories": getattr(lead, "calories", None),
        }

        try:
            text, markup = build_lead_card(payload)
        except Exception as exc:  # noqa: BLE001 - keep iterating over leads
            logger.exception("Failed to build lead card for %s: %s", payload.get("tg_id"), exc)
            continue

        try:
            await message.answer(text, parse_mode="HTML", reply_markup=markup)
        except Exception as exc:  # noqa: BLE001 - continue with other leads
            logger.error("Failed to send lead card for %s: %s", payload.get("tg_id"), exc)
            continue

        await asyncio.sleep(0.05)


async def _handle_all_leads_request(message: Message, page: int, window: str) -> None:
    try:
        leads, total_count, total_pages, current_page, window_key = await _load_leads_page(page, window)
    except Exception as exc:  # noqa: BLE001 - log and inform the admin
        logger.exception("Failed to load leads list: %s", exc)
        await message.answer(get_text("admin.leads.load_error"))
        return

    if total_count <= 0 or not leads:
        await message.answer(get_text("admin.leads.empty_list"))
        return

    await _send_lead_cards(message, leads)

    pager_text = _format_leads_pager_text(current_page, total_pages, total_count, window_key)
    pager_markup = _build_leads_pager_markup(current_page, total_pages, window_key)

    try:
        await message.answer(pager_text, reply_markup=pager_markup)
    except Exception as exc:  # noqa: BLE001 - log only
        logger.error("Failed to send leads pager: %s", exc)


@rate_limit
@error_handler
async def cmd_all_leads(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page, window = _parse_leads_command_args(args)

    await _handle_all_leads_request(message, page, window)


@rate_limit
@error_handler
async def cmd_all_leads_today(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page = _parse_page_arg(args)

    await _handle_all_leads_request(message, page, "today")


@rate_limit
@error_handler
async def cmd_all_leads_7d(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin_access(message):
        return

    args = command.args if command else None
    page = _parse_page_arg(args)

    await _handle_all_leads_request(message, page, "7d")


def _parse_tg_id_from_callback(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None

    try:
        return int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


@rate_limit
@error_handler
async def paginate_leads(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        await callback.answer(get_text("admin.leads.no_permission_alert"), show_alert=True)
        return

    data = callback.data or ""
    parts = data.split(":", 2)
    if len(parts) != 3:
        await callback.answer(get_text("admin.leads.invalid_request"), show_alert=True)
        return

    try:
        requested_page = int(parts[1])
    except ValueError:
        requested_page = 1

    window = parts[2]

    try:
        leads, total_count, total_pages, current_page, window_key = await _load_leads_page(requested_page, window)
    except Exception as exc:  # noqa: BLE001 - show alert and keep the pager intact
        logger.exception("Failed to paginate leads: %s", exc)
        if callback.message:
            try:
                await callback.message.edit_text(
                    get_text("admin.leads.load_error"),
                    reply_markup=None,
                )
            except Exception as edit_exc:  # noqa: BLE001 - log only
                logger.warning("Failed to update pager message after error: %s", edit_exc)
        await callback.answer(get_text("admin.leads.load_error_alert"), show_alert=True)
        return

    if total_count <= 0 or not leads:
        if callback.message:
            try:
                await callback.message.edit_text(
                    get_text("admin.leads.empty_list"),
                    reply_markup=None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to update pager message for empty list: %s", exc)
        await callback.answer()
        return

    if callback.message:
        try:
            await callback.message.edit_text(
                _format_leads_pager_text(current_page, total_pages, total_count, window_key),
                reply_markup=_build_leads_pager_markup(current_page, total_pages, window_key),
            )
        except Exception as exc:  # noqa: BLE001 - keep flow resilient
            logger.warning("Failed to edit leads pager message: %s", exc)

        await _send_lead_cards(callback.message, leads)
    else:
        logger.warning("Callback without message for leads pagination")

    await callback.answer()


@rate_limit
@error_handler
async def lead_delete_request(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to initiate lead deletion", callback.from_user.id
        )
        await callback.answer(get_text("admin.leads.no_permission_alert"), show_alert=True)
        return

    data = callback.data or ""
    tg_id = _parse_tg_id_from_callback(data, "lead_delete:")
    if tg_id is None:
        logger.error("Failed to parse lead deletion request from data: %s", data)
        await callback.answer(get_text("admin.leads.invalid_request"), show_alert=True)
        return

    if not callback.message:
        logger.warning("Lead delete request without message for tg_id %s", tg_id)
        await callback.answer(get_text("admin.leads.missing_message"), show_alert=True)
        return

    confirmation_text = get_text("admin.leads.delete_prompt", tg_id=tg_id)

    try:
        await callback.message.reply(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=_build_lead_delete_confirmation_markup(tg_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send lead delete confirmation for %s: %s", tg_id, exc)
        await callback.answer(get_text("admin.leads.load_error_alert"), show_alert=True)
        return

    await callback.answer()


def _build_lead_delete_confirmation_markup(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_button_text(BUTTON_CONFIRM_YES),
                    callback_data=f"lead_delete_confirm:{tg_id}",
                ),
                InlineKeyboardButton(
                    text=get_button_text(BUTTON_CONFIRM_NO),
                    callback_data="lead_delete_cancel",
                ),
            ]
        ]
    )


@rate_limit
@error_handler
async def lead_delete_cancel(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to cancel lead deletion", callback.from_user.id
        )
        await callback.answer(get_text("admin.leads.no_permission_alert"), show_alert=True)
        return

    if callback.message:
        try:
            await callback.message.delete()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete lead delete confirmation message: %s", exc)

    await callback.answer(get_text("admin.leads.delete_cancelled_alert"))


@rate_limit
@error_handler
async def lead_delete_confirm(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    if not _is_admin(callback.from_user.id):
        logger.warning(
            "Non-admin user %s attempted to confirm lead deletion", callback.from_user.id
        )
        await callback.answer(get_text("admin.leads.no_permission_alert"), show_alert=True)
        return

    data = callback.data or ""
    tg_id = _parse_tg_id_from_callback(data, "lead_delete_confirm:")
    if tg_id is None:
        logger.error("Failed to parse lead deletion confirmation from data: %s", data)
        await callback.answer(get_text("admin.leads.invalid_request"), show_alert=True)
        return

    delete_result = await safe_db_operation(delete_user_by_tg_id, tg_id)
    if not delete_result:
        if callback.message:
            try:
                await callback.message.edit_text(
                    get_text("admin.leads.delete_failed"),
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to update confirmation message after error: %s", exc)
        await callback.answer(get_text("admin.leads.delete_failed_alert"), show_alert=True)
        return

    if callback.message:
        success_text = get_text("admin.leads.delete_success", tg_id=tg_id)
        try:
            await callback.message.edit_text(
                success_text,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to edit confirmation message after deletion: %s", exc)

        original_message = callback.message.reply_to_message
        if original_message:
            try:
                await original_message.delete()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to delete original lead card message: %s", exc)

    await callback.answer(get_text("admin.leads.delete_success_alert"))

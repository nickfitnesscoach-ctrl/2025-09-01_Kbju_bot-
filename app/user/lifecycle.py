"""Lifecycle handlers reacting to chat member updates."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from app.database.requests import delete_user_by_tg_id, get_user
from app.texts import get_text
from utils.notifications import notify_lead_card

from .shared import safe_db_operation

logger = logging.getLogger(__name__)


def register(router: Router) -> None:
    router.my_chat_member.register(handle_private_chat_member_update, F.chat.type == "private")


async def handle_private_chat_member_update(event: ChatMemberUpdated) -> None:
    """Notify admin when a user blocks the bot or leaves the chat."""

    new_status = event.new_chat_member.status
    if new_status not in {ChatMemberStatus.KICKED, ChatMemberStatus.LEFT}:
        return

    lead_user = event.from_user or event.new_chat_member.user
    if not lead_user or not lead_user.id:
        logger.warning("Chat member update without user info: %s", event)
        return

    lead_id = lead_user.id
    should_delete_lead = new_status == ChatMemberStatus.KICKED

    db_user = await safe_db_operation(get_user, lead_id)
    if db_user is False:
        logger.warning("Failed to fetch user %s for leave notification", lead_id)
        db_user = None

    if db_user:
        lead_payload: dict[str, Any] = {
            "tg_id": db_user.tg_id,
            "username": getattr(db_user, "username", None),
            "first_name": getattr(db_user, "first_name", None),
            "goal": getattr(db_user, "goal", None),
            "calories": getattr(db_user, "calories", None),
        }
    else:
        lead_payload = {
            "tg_id": lead_id,
            "username": getattr(lead_user, "username", None),
            "first_name": getattr(lead_user, "first_name", None),
            "goal": None,
            "calories": None,
        }

    try:
        await notify_lead_card(lead_payload, title=get_text("admin.leads.left_title"))
        logger.info("Sent leave notification for user %s", lead_id)
    except Exception as exc:  # noqa: BLE001 - do not interrupt processing
        logger.exception("Failed to send leave notification for user %s: %s", lead_id, exc)

    if should_delete_lead:
        delete_result = await safe_db_operation(delete_user_by_tg_id, lead_id)
        if delete_result:
            logger.info("Deleted lead %s after bot block", lead_id)
        else:
            logger.warning("Failed to delete lead %s after bot block", lead_id)

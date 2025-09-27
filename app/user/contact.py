"""Handlers for contact requests between leads and the admin."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.types import Message

from app.contact_requests import contact_request_registry
from app.texts import get_text
from config import ADMIN_CHAT_ID
from utils.notifications import CONTACT_REQUEST_MESSAGE

from .shared import error_handler, rate_limit

logger = logging.getLogger(__name__)


def register(router: Router) -> None:
    router.message.register(forward_lead_contact_response, _is_contact_response)


async def _is_contact_response(message: Message) -> bool:
    if not message.from_user:
        return False
    if message.chat.type != ChatType.PRIVATE:
        return False
    if message.reply_to_message and message.reply_to_message.text == CONTACT_REQUEST_MESSAGE:
        return True
    return await contact_request_registry.is_pending(message.from_user.id)


@rate_limit
@error_handler
async def forward_lead_contact_response(message: Message) -> None:
    """Forward the lead response to the admin after a contact request."""

    if not message.from_user:
        return

    lead_id = message.from_user.id
    logger.info("Forwarding contact reply from lead %s to admin", lead_id)

    if ADMIN_CHAT_ID is None:
        logger.warning("Cannot forward contact reply because ADMIN_CHAT_ID is not configured")
        await _notify_lead_about_failure(message)
        return

    try:
        await message.forward(chat_id=ADMIN_CHAT_ID)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
        logger.error("Failed to forward contact reply from %s: %s", lead_id, exc)
        await _notify_lead_about_failure(message)
        return
    except Exception as exc:  # noqa: BLE001 - make sure we do not interrupt user flow
        logger.exception("Unexpected error while forwarding contact reply from %s: %s", lead_id, exc)
        await _notify_lead_about_failure(message)
        return

    await contact_request_registry.remove(lead_id)

    try:
        await message.answer(get_text("contact.forward_success"))
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.warning("Failed to confirm contact reply to lead %s: %s", lead_id, exc)
    except Exception as exc:  # noqa: BLE001 - keep flow resilient
        logger.exception("Unexpected error while confirming contact reply to %s: %s", lead_id, exc)


async def _notify_lead_about_failure(message: Message) -> None:
    try:
        await message.answer(get_text("contact.forward_failure"))
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.warning("Failed to notify lead about failed contact delivery: %s", exc)
    except Exception as exc:  # noqa: BLE001 - fallback logging only
        logger.exception("Unexpected error while notifying lead about failed contact delivery: %s", exc)

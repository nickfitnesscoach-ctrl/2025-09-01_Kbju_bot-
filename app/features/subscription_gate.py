"""Subscription gate flow for requiring channel membership."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.texts import get_text
from config import (
    ALLOW_GATE_FALLBACK_PASS,
    CHANNEL_ID_OR_USERNAME,
    CHANNEL_URL,
    ENABLE_SUBSCRIPTION_GATE,
)

MessageOrCb = Union[Message, CallbackQuery]

CHECK_CALLBACK_DATA = "sub_gate_check"

logger = logging.getLogger(__name__)


async def should_gate() -> bool:
    """Return True if the subscription gate must be shown."""

    return bool(ENABLE_SUBSCRIPTION_GATE and CHANNEL_ID_OR_USERNAME)


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    """Check whether the user is subscribed to the configured channel."""

    if not await should_gate():
        return True

    try:
        member = await bot.get_chat_member(CHANNEL_ID_OR_USERNAME, user_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
        logger.warning(
            "Subscription gate: API error while checking membership for user %s: %s",
            user_id,
            exc,
        )
        if ALLOW_GATE_FALLBACK_PASS:
            logger.warning(
                "Subscription gate: allowing user %s due to ALLOW_GATE_FALLBACK_PASS after API error",
                user_id,
            )
            return True
        return False
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning(
            "Subscription gate: unexpected error while checking membership for user %s: %s",
            user_id,
            exc,
        )
        if ALLOW_GATE_FALLBACK_PASS:
            logger.warning(
                "Subscription gate: allowing user %s due to ALLOW_GATE_FALLBACK_PASS after unexpected error",
                user_id,
            )
            return True
        return False

    status = getattr(member, "status", None)
    if status in {"member", "administrator", "creator"}:
        logger.info("Subscription gate: user %s is subscribed (status=%s)", user_id, status)
        return True

    logger.info("Subscription gate: user %s is not subscribed (status=%s)", user_id, status)
    return False


async def ensure_subscription_and_continue(
    bot: Bot,
    user_id: int,
    message_or_cb: MessageOrCb,
    on_success: Callable[[], Awaitable[None]],
) -> None:
    """Ensure the user passes the subscription gate before continuing."""

    try:
        gating_enabled = await should_gate()
        if not gating_enabled:
            await _run_on_success(message_or_cb, on_success)
            return

        is_subscribed = await is_user_subscribed(bot, user_id)
        if is_subscribed:
            success_text = None
            if isinstance(message_or_cb, CallbackQuery) and message_or_cb.data == CHECK_CALLBACK_DATA:
                success_text = get_text("subscription_gate.success")
            await _run_on_success(message_or_cb, on_success, success_text=success_text)
            return

        # User is not subscribed — show gate or inform about missing subscription.
        if isinstance(message_or_cb, CallbackQuery) and message_or_cb.data == CHECK_CALLBACK_DATA:
            await _notify_not_subscribed(message_or_cb)
        else:
            await _show_gate_prompt(message_or_cb)
    except Exception as exc:  # pragma: no cover - fail-safe guard
        logger.exception("Subscription gate: unexpected failure for user %s: %s", user_id, exc)
        if ALLOW_GATE_FALLBACK_PASS:
            logger.warning(
                "Subscription gate: allowing user %s due to ALLOW_GATE_FALLBACK_PASS after failure",
                user_id,
            )
            await _run_on_success(message_or_cb, on_success)


async def _run_on_success(
    message_or_cb: MessageOrCb,
    on_success: Callable[[], Awaitable[None]],
    *,
    success_text: str | None = None,
) -> None:
    try:
        await on_success()
    except Exception:
        logger.exception("Subscription gate: on_success handler failed")
        raise
    finally:
        if isinstance(message_or_cb, CallbackQuery):
            await _safe_answer(message_or_cb, success_text)


async def _notify_not_subscribed(callback: CallbackQuery) -> None:
    logger.info("Subscription gate: user %s attempted to continue without subscription", callback.from_user.id if callback.from_user else "unknown")
    await _safe_answer(callback, get_text("subscription_gate.not_yet"), show_alert=True)


async def _show_gate_prompt(message_or_cb: MessageOrCb) -> None:
    prompt_text = get_text("subscription_gate.prompt")
    keyboard = _build_subscription_keyboard(_infer_back_callback_data(message_or_cb))

    if isinstance(message_or_cb, CallbackQuery):
        logger.info(
            "Subscription gate: showing gate to user %s",
            message_or_cb.from_user.id if message_or_cb.from_user else "unknown",
        )
        message = message_or_cb.message
        if message:
            try:
                await message.edit_text(prompt_text, reply_markup=keyboard, parse_mode="HTML")
            except TelegramBadRequest as exc:
                logger.warning(
                    "Subscription gate: failed to edit message for gate screen: %s",
                    exc,
                )
                try:
                    await message.answer(prompt_text, reply_markup=keyboard, parse_mode="HTML")
                except Exception as send_exc:  # pragma: no cover - safety net
                    logger.warning(
                        "Subscription gate: failed to send gate prompt message: %s",
                        send_exc,
                    )
        await _safe_answer(message_or_cb, None)
    else:
        logger.info(
            "Subscription gate: showing gate to user %s via message",
            message_or_cb.from_user.id if message_or_cb.from_user else "unknown",
        )
        try:
            await message_or_cb.answer(prompt_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:  # pragma: no cover - safety net
            logger.warning("Subscription gate: failed to send gate prompt via message: %s", exc)


def _build_subscription_keyboard(back_callback_data: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    open_button_text = get_text("subscription_gate.open_button")
    if CHANNEL_URL:
        rows.append([InlineKeyboardButton(text=open_button_text, url=CHANNEL_URL)])

    check_button_text = get_text("subscription_gate.check_button")
    rows.append([InlineKeyboardButton(text=check_button_text, callback_data=CHECK_CALLBACK_DATA)])

    back_button_text = get_text("subscription_gate.back_button")
    rows.append([InlineKeyboardButton(text=back_button_text, callback_data=back_callback_data)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _infer_back_callback_data(message_or_cb: MessageOrCb) -> str:
    default_target = "main_menu"

    if isinstance(message_or_cb, CallbackQuery):
        message = message_or_cb.message
        if message and message.reply_markup:
            for row in message.reply_markup.inline_keyboard:
                for button in row:
                    data = getattr(button, "callback_data", None)
                    if not data or data == CHECK_CALLBACK_DATA:
                        continue
                    if data == "profile":
                        return "main_menu"
                    if data == "main_menu":
                        return "profile"
        if message_or_cb.data == CHECK_CALLBACK_DATA:
            return default_target
    return default_target


async def _safe_answer(
    callback: CallbackQuery,
    text: str | None,
    *,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
        pass
    except TelegramNetworkError as exc:
        logger.warning("Subscription gate: failed to answer callback due to network error: %s", exc)
    except Exception as exc:  # pragma: no cover - safety net
        logger.warning("Subscription gate: failed to answer callback: %s", exc)

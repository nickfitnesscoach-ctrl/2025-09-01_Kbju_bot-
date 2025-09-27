"""Utility helpers shared between user handlers."""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Awaitable, Callable

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message

from app.constants import (
    DB_OPERATION_RETRIES,
    DB_OPERATION_RETRY_DELAY,
    DB_OPERATION_TIMEOUT,
    MAX_TEXT_LENGTH,
    USER_REQUESTS_LIMIT,
    USER_REQUESTS_WINDOW,
)
from sqlalchemy.exc import OperationalError
from app.database.requests import update_last_activity
from app.texts import get_text

logger = logging.getLogger(__name__)


AsyncHandler = Callable[..., Awaitable[Any]]


_user_requests: dict[int, list[float]] = {}


def sanitize_text(value: Any, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Escape HTML and limit message length."""

    text = "" if value is None else str(value)
    text = html.escape(text)
    return text if len(text) <= max_length else f"{text[:max_length]}…"


async def safe_db_operation(operation: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Execute a DB coroutine with a timeout, retries and unified logging."""

    attempt = 0
    last_error: Exception | None = None

    while attempt < DB_OPERATION_RETRIES:
        try:
            return await asyncio.wait_for(operation(*args, **kwargs), timeout=DB_OPERATION_TIMEOUT)
        except asyncio.TimeoutError as exc:
            logger.error("DB timeout: %s", getattr(operation, "__name__", str(operation)))
            last_error = exc
            break
        except OperationalError as exc:
            last_error = exc
            attempt += 1
            if attempt >= DB_OPERATION_RETRIES:
                logger.exception(
                    "DB operational error in %s after %s attempts: %s",
                    getattr(operation, "__name__", str(operation)),
                    attempt,
                    exc,
                )
                break

            delay = DB_OPERATION_RETRY_DELAY * attempt
            logger.warning(
                "DB operational error in %s (attempt %s/%s): %s | retrying in %.2fs",
                getattr(operation, "__name__", str(operation)),
                attempt,
                DB_OPERATION_RETRIES,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            continue
        except Exception as exc:  # noqa: BLE001 - defensive logging
            logger.exception(
                "DB error in %s: %s",
                getattr(operation, "__name__", str(operation)),
                exc,
            )
            last_error = exc
            break
        else:
            break

    if last_error is not None:
        logger.debug("safe_db_operation returning False due to error: %s", last_error)
    return False


def rate_limit(handler: AsyncHandler) -> AsyncHandler:
    """Limit how often a single user can trigger the handler."""

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        user_id = _extract_user_id(args, kwargs)
        if user_id:
            now = datetime.utcnow().timestamp()
            bucket = _user_requests.setdefault(user_id, [])
            bucket[:] = [moment for moment in bucket if now - moment < USER_REQUESTS_WINDOW]
            if len(bucket) >= USER_REQUESTS_LIMIT:
                logger.warning("Rate limit exceeded for user %s", user_id)
                return None
            bucket.append(now)

        return await handler(*args, **kwargs)

    return wrapper


def error_handler(handler: AsyncHandler) -> AsyncHandler:
    """Convert Telegram/network errors into safe replies."""

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await handler(*args, **kwargs)
        except TelegramBadRequest as exc:
            logger.error("TelegramBadRequest in %s: %s", handler.__name__, exc)
            if "message is not modified" in str(exc):
                callback = _extract_callback_query(args, kwargs)
                if callback:
                    try:
                        await callback.answer()
                    except (TelegramBadRequest, TelegramNetworkError) as answer_exc:
                        logger.warning("Callback answer failed: %s", answer_exc)
                return None

            message = _extract_message(args, kwargs)
            if message:
                try:
                    from app.keyboards import back_to_menu  # local import to avoid circular deps

                    await message.answer(
                        get_text("errors.general_error"),
                        reply_markup=back_to_menu(),
                        parse_mode="HTML",
                    )
                except Exception as reply_exc:  # noqa: BLE001 - defensive UI logging
                    logger.exception("Unhandled UI error: %s", reply_exc)
            return None
        except TelegramRetryAfter as exc:
            logger.warning("Rate limited by Telegram: %s", exc)
            await asyncio.sleep(exc.retry_after)
            return None
        except Exception as exc:  # noqa: BLE001 - defensive catch-all
            logger.exception("Unexpected error in %s: %s", handler.__name__, exc)
            message = _extract_message(args, kwargs)
            if message:
                try:
                    from app.keyboards import back_to_menu  # local import to avoid circular deps

                    await message.answer(
                        get_text("errors.general_error"),
                        reply_markup=back_to_menu(),
                        parse_mode="HTML",
                    )
                except Exception as reply_exc:  # noqa: BLE001 - defensive UI logging
                    logger.exception("Unhandled UI error: %s", reply_exc)
            return None

    return wrapper


def track_user_activity(source: str) -> Callable[[AsyncHandler], AsyncHandler]:
    """Update last activity timestamp after the handler completes."""

    def decorator(handler: AsyncHandler) -> AsyncHandler:
        @wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user_id = _extract_user_id(args, kwargs)
            try:
                return await handler(*args, **kwargs)
            finally:
                if user_id:
                    try:
                        await _touch_user_activity(user_id, source=source)
                    except asyncio.CancelledError:  # pragma: no cover - cooperate with shutdown
                        raise
                    except Exception as exc:  # noqa: BLE001 - do not break handler flow
                        logger.warning(
                            "Failed to update last activity for user %s via %s: %s",
                            user_id,
                            source,
                            exc,
                        )

        return wrapper

    return decorator


async def _touch_user_activity(user_id: int, *, source: str) -> None:
    result = await safe_db_operation(update_last_activity, user_id)
    if result:
        logger.debug("Last activity updated for user %s via %s", user_id, source)
    else:
        logger.debug("Last activity update skipped for user %s via %s", user_id, source)


def _extract_message(args: Any, kwargs: Any) -> Message | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Message):
            return value
        if isinstance(value, CallbackQuery) and value.message:
            return value.message
    return None


def _extract_callback_query(args: Any, kwargs: Any) -> CallbackQuery | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, CallbackQuery):
            return value
    return None


def _extract_user_id(args: Any, kwargs: Any) -> int | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Message) and value.from_user:
            return value.from_user.id
        if isinstance(value, CallbackQuery) and value.from_user:
            return value.from_user.id
    return None


__all__ = [
    "sanitize_text",
    "safe_db_operation",
    "rate_limit",
    "error_handler",
    "track_user_activity",
]

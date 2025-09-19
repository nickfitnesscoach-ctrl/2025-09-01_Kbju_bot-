"""Асинхронные запросы к базе данных и служебные уведомления."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from app.database.models import User, async_session
from utils.notifications import notify_lead_card, notify_new_hot_lead


logger = logging.getLogger(__name__)


async def set_user(tg_id: int, username: str | None = None, first_name: str | None = None) -> None:
    """Создать или обновить пользователя и отправить уведомления о новом лиде."""

    new_lead_created = False
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if not user:
            new_lead_created = True
            session.add(
                User(
                    tg_id=tg_id,
                    username=username,
                    first_name=first_name,
                    funnel_status="new",
                    priority_score=0,
                )
            )
        else:
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            user.updated_at = datetime.utcnow()

        await session.commit()

    if not new_lead_created:
        return

    lead_payload: dict[str, Any] = {
        "tg_id": tg_id,
        "username": username,
        "first_name": first_name,
    }

    try:
        await notify_lead_card(lead_payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send lead card notification: %s", exc)


async def get_user(tg_id: int) -> User | None:
    """Получить пользователя по Telegram ID."""

    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_id == tg_id))


async def delete_user_by_tg_id(tg_id: int) -> bool:
    """Удалить пользователя по Telegram ID."""

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if not user:
            logger.info("User with tg_id %s not found for deletion", tg_id)
            return False

        try:
            await session.delete(user)
            await session.commit()
            return True
        except IntegrityError as exc:
            await session.rollback()

            soft_deleted = False
            try:
                user = await session.scalar(select(User).where(User.tg_id == tg_id))
            except Exception:  # noqa: BLE001
                user = None

            if user and hasattr(user, "deleted_at"):
                setattr(user, "deleted_at", datetime.utcnow())
                if hasattr(user, "updated_at"):
                    user.updated_at = datetime.utcnow()
                session.add(user)
                try:
                    await session.commit()
                    soft_deleted = True
                except Exception as soft_exc:  # noqa: BLE001
                    await session.rollback()
                    logger.exception("Failed to soft delete user %s: %s", tg_id, soft_exc)

            elif user and hasattr(user, "is_deleted"):
                setattr(user, "is_deleted", True)
                if hasattr(user, "updated_at"):
                    user.updated_at = datetime.utcnow()
                session.add(user)
                try:
                    await session.commit()
                    soft_deleted = True
                except Exception as soft_exc:  # noqa: BLE001
                    await session.rollback()
                    logger.exception("Failed to soft delete user %s: %s", tg_id, soft_exc)

            if soft_deleted:
                logger.info("Soft-deleted user %s due to integrity constraints", tg_id)
                return True

            logger.exception("Integrity error while deleting user %s: %s", tg_id, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            logger.exception("Failed to delete user %s: %s", tg_id, exc)
            return False


async def update_user_data(tg_id: int, **kwargs: Any) -> User | None:
    """Обновить данные пользователя."""

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = datetime.utcnow()
            await session.commit()

        return user


async def update_user_status(
    tg_id: int,
    status: str,
    priority: str | None = None,
    first_name: str | None = None,
    priority_score: int | None = None,
) -> User | None:
    """Обновить статус воронки лидов и дополнительные данные."""

    user_snapshot: dict[str, Any] | None = None
    should_check_hot_lead = False
    updated_user: User | None = None

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if user:
            user.funnel_status = status
            if priority:
                user.priority = priority
            if first_name:
                user.first_name = first_name
            if priority_score is not None:
                user.priority_score = priority_score
            user.updated_at = datetime.utcnow()

            user_snapshot = {
                "tg_id": user.tg_id,
                "username": user.username,
                "first_name": user.first_name,
                "goal": user.goal,
                "calories": user.calories,
                "priority": user.priority,
                "priority_score": user.priority_score,
                "funnel_status": user.funnel_status,
            }

            should_check_hot_lead = status.startswith("hotlead_")

            await session.commit()
            updated_user = user

        else:
            logger.debug("User with tg_id %s not found for status update", tg_id)

    if should_check_hot_lead and user_snapshot:
        if await was_hot_lead_notified(tg_id):
            logger.debug("Hot lead notification already sent for user %s; skipping", tg_id)
        else:
            notification_sent = await notify_new_hot_lead(user_snapshot)
            if notification_sent:
                await mark_hot_lead_notified(tg_id)

    return updated_user


async def get_calculated_users_for_timer() -> list[User]:
    """Получить пользователей со статусом calculated для таймера."""

    async with async_session() as session:
        users = await session.scalars(
            select(User).where(
                User.funnel_status == "calculated",
                User.calculated_at.isnot(None),
            )
        )
        return users.all()


async def get_hot_leads() -> list[User]:
    """Получить все горячие лиды отсортированные по приоритету."""

    async with async_session() as session:
        users = await session.scalars(
            select(User)
            .where(User.funnel_status.like("%hotlead%"))
            .order_by(
                desc(User.priority_score),
                desc(User.updated_at),
            )
        )
        return users.all()


async def get_started_leads(
    offset: int = 0,
    limit: int = 20,
    since: datetime | None = None,
) -> list[User]:
    """Получить пользователей, начавших воронку (/start)."""

    async with async_session() as session:
        query = select(User).where(User.created_at.isnot(None))

        if since is not None:
            query = query.where(User.created_at >= since)

        query = query.order_by(desc(User.created_at))

        if offset:
            query = query.offset(max(offset, 0))

        if limit:
            query = query.limit(limit)

        users = await session.scalars(query)
        return users.all()


async def count_started_leads(since: datetime | None = None) -> int:
    """Подсчитать количество пользователей, начавших воронку."""

    async with async_session() as session:
        query = select(func.count()).select_from(User).where(User.created_at.isnot(None))

        if since is not None:
            query = query.where(User.created_at >= since)

        result = await session.scalar(query)
        return int(result or 0)


async def was_hot_lead_notified(tg_id: int) -> bool:
    """Проверить, было ли отправлено уведомление о горячем лиде."""

    async with async_session() as session:
        notified_at = await session.scalar(
            select(User.hot_lead_notified_at).where(User.tg_id == tg_id)
        )
        return notified_at is not None


async def mark_hot_lead_notified(tg_id: int) -> None:
    """Отметить, что уведомление о горячем лиде отправлено."""

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if not user:
            logger.debug("Cannot mark hot lead notification for missing user %s", tg_id)
            return

        user.hot_lead_notified_at = datetime.utcnow()
        await session.commit()

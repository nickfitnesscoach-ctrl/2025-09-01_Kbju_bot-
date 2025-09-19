"""Асинхронные запросы к базе данных и служебные уведомления."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from app.database.models import User, async_session
from utils.notifications import notify_lead_card


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

            await session.commit()

        return user


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

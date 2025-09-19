from datetime import datetime
import logging

from sqlalchemy import desc, select

from app.database.models import User, async_session
from utils.notifications import notify_new_lead


logger = logging.getLogger(__name__)


async def set_user(tg_id, username=None, first_name=None):
    """Создать или обновить пользователя"""
    new_lead_created = False
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if not user:
            new_lead_created = True
            session.add(User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                funnel_status='new',
                priority_score=0  # Устанавливаем базовый приоритет
            ))
        else:
            # Обновляем username и first_name если они изменились
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            user.updated_at = datetime.utcnow()

        await session.commit()

    if new_lead_created:
        contact = f"@{username}" if username else f"tg_id: {tg_id}"
        try:
            await notify_new_lead(first_name or "Не указано", contact)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send new lead notification: %s", exc)


async def get_user(tg_id):
    """Получить пользователя по Telegram ID"""
    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_id == tg_id))


async def update_user_data(tg_id, **kwargs):
    """Обновить данные пользователя"""
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            user.updated_at = datetime.utcnow()
            await session.commit()
            
        return user


async def update_user_status(tg_id, status, priority=None, first_name=None, priority_score=None):
    """Обновить статус воронки лидов и дополнительные данные"""
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


async def get_calculated_users_for_timer():
    """Получить пользователей со статусом calculated для таймера"""
    async with async_session() as session:
        users = await session.scalars(
            select(User).where(
                User.funnel_status == 'calculated',
                User.calculated_at.isnot(None)
            )
        )
        return users.all()


async def get_hot_leads():
    """Получить все горячие лиды отсортированные по приоритету"""
    async with async_session() as session:
        users = await session.scalars(
            select(User).where(
                User.funnel_status.like('%hotlead%')
            ).order_by(
                desc(User.priority_score),  # Сначала с высоким приоритетом
                desc(User.updated_at)       # Потом по времени обновления
            )
        )
        return users.all()

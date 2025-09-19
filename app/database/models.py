from datetime import datetime
import logging

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, inspect, text
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.exc import SQLAlchemyError

try:  # pragma: no cover - совместимость разных версий SQLAlchemy
    from sqlalchemy.schema import AddColumn
except ImportError:  # pragma: no cover - fallback для SQLAlchemy 2.0+
    AddColumn = None  # type: ignore[assignment]

from config import DB_URL, DEBUG

engine = create_async_engine(url=DB_URL,
                             echo=DEBUG)

async_session = async_sessionmaker(engine)

logger = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    
    # Существующие поля
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id = mapped_column(BigInteger, unique=True)
    
    # Новые поля для КБЖУ
    username: Mapped[str] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=True)
    gender: Mapped[str] = mapped_column(String(10), nullable=True)  # male/female
    age: Mapped[int] = mapped_column(Integer, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=True)
    height: Mapped[int] = mapped_column(Integer, nullable=True)
    activity: Mapped[str] = mapped_column(String(20), nullable=True)  # low/moderate/high/very_high
    goal: Mapped[str] = mapped_column(String(20), nullable=True)  # weight_loss/maintenance/weight_gain
    
    # Рассчитанные КБЖУ
    calories: Mapped[int] = mapped_column(Integer, nullable=True)
    proteins: Mapped[int] = mapped_column(Integer, nullable=True)
    fats: Mapped[int] = mapped_column(Integer, nullable=True)
    carbs: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # Статусы воронки лидов
    funnel_status: Mapped[str] = mapped_column(String(20), default='new')  # new/calculated/hotlead/coldlead
    priority: Mapped[str] = mapped_column(String(20), nullable=True)  # nutrition/training/schedule
    priority_score: Mapped[int] = mapped_column(Integer, default=0)  # Числовой приоритет для сортировки
    hot_lead_notified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # для таймера


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_hot_lead_notified_column)


def _ensure_hot_lead_notified_column(sync_conn) -> None:
    """Create the hot_lead_notified_at column if it is missing."""

    inspector = inspect(sync_conn)
    columns = {column["name"] for column in inspector.get_columns(User.__tablename__)}

    if "hot_lead_notified_at" in columns:
        logger.debug("users.hot_lead_notified_at already exists")
        return

    logger.info("Adding users.hot_lead_notified_at column for hot lead notifications")

    try:
        if AddColumn is not None:
            ddl = AddColumn(
                User.__table__,
                Column("hot_lead_notified_at", DateTime, nullable=True),
            )
            sync_conn.execute(ddl)
        else:
            sync_conn.execute(
                text("ALTER TABLE users ADD COLUMN hot_lead_notified_at DATETIME")
            )
    except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to add users.hot_lead_notified_at column: %s", exc)
        refreshed_columns = {
            column["name"] for column in inspector.get_columns(User.__tablename__)
        }
        if "hot_lead_notified_at" not in refreshed_columns:
            raise

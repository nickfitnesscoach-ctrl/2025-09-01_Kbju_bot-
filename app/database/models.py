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
from app.database.migrations import migrate_drop_drip_columns

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

    # Признаки активности и прогресса drip-воронки
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    drip_stage: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default=text("0")
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # для таймера


async def async_main():
    migrate_drop_drip_columns(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_additional_user_columns)


def _ensure_additional_user_columns(sync_conn) -> None:
    """Гарантировать наличие дополнительных колонок в таблице users."""

    inspector = inspect(sync_conn)
    existing = {column["name"] for column in inspector.get_columns(User.__tablename__)}

    def _ensure_column(
        column_name: str,
        column: Column,
        fallback_sql: str,
        log_message: str,
    ) -> None:
        if column_name in existing:
            logger.debug("users.%s already exists", column_name)
            return

        logger.info(log_message)

        try:
            if AddColumn is not None:
                ddl = AddColumn(User.__table__, column)
                sync_conn.execute(ddl)
            else:
                sync_conn.execute(text(fallback_sql))
        except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to add users.%s column: %s", column_name, exc)
            refreshed = {
                col["name"] for col in inspector.get_columns(User.__tablename__)
            }
            if column_name not in refreshed:
                raise

    _ensure_column(
        "hot_lead_notified_at",
        Column("hot_lead_notified_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN hot_lead_notified_at DATETIME",
        "Adding users.hot_lead_notified_at column for hot lead notifications",
    )
    _ensure_column(
        "last_activity_at",
        Column("last_activity_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN last_activity_at DATETIME",
        "Adding users.last_activity_at column for drip follow-ups",
    )
    _ensure_column(
        "drip_stage",
        Column(
            "drip_stage",
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
        "ALTER TABLE users ADD COLUMN drip_stage INTEGER NOT NULL DEFAULT 0",
        "Adding users.drip_stage column for drip follow-ups",
    )

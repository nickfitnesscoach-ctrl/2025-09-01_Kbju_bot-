from datetime import datetime
import logging

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    inspect,
    text,
)
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


_REQUIRED_USER_COLUMNS: set[str] = {
    "id",
    "tg_id",
    "username",
    "first_name",
    "gender",
    "age",
    "weight",
    "height",
    "activity",
    "goal",
    "calories",
    "proteins",
    "fats",
    "carbs",
    "funnel_status",
    "priority",
    "priority_score",
    "created_at",
    "updated_at",
    "calculated_at",
    "hot_lead_notified_at",
    "last_activity_at",
    "drip_stage",
}

_COLUMN_FALLBACKS: dict[str, tuple[Column, str]] = {
    "hot_lead_notified_at": (
        Column("hot_lead_notified_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN hot_lead_notified_at DATETIME",
    ),
    "last_activity_at": (
        Column("last_activity_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN last_activity_at DATETIME",
    ),
    "drip_stage": (
        Column(
            "drip_stage",
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
        "ALTER TABLE users ADD COLUMN drip_stage INTEGER NOT NULL DEFAULT 0",
    ),
    "updated_at": (
        Column("updated_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN updated_at DATETIME",
    ),
    "calculated_at": (
        Column("calculated_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN calculated_at DATETIME",
    ),
}


async def async_main():
    migrate_drop_drip_columns(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_user_schema)


def _ensure_user_schema(sync_conn) -> None:
    """Проверить и восстановить схему таблицы ``users``."""

    inspector = inspect(sync_conn)
    existing = {
        column["name"] for column in inspector.get_columns(User.__tablename__)
    }

    logger.info("[schema] users: existing columns -> %s", sorted(existing))

    missing = _REQUIRED_USER_COLUMNS - existing
    unexpected = existing - _REQUIRED_USER_COLUMNS

    if unexpected:
        logger.warning(
            "[schema] users: unexpected columns detected -> %s", sorted(unexpected)
        )

    if not missing:
        logger.info("OK: users has all required columns")
    else:
        logger.warning(
            "[schema] users: missing columns -> %s | applying ensure_columns fallback",
            sorted(missing),
        )

    for column_name in sorted(missing):
        column_spec = _COLUMN_FALLBACKS.get(column_name)
        if column_spec is None:
            raise RuntimeError(
                f"users column {column_name} is missing and no fallback DDL is defined"
            )

        column, fallback_sql = column_spec
        logger.info("[schema] users: adding column %s", column_name)

        try:
            if AddColumn is not None:
                ddl = AddColumn(User.__table__, column)
                sync_conn.execute(ddl)
            else:
                sync_conn.execute(text(fallback_sql))
        except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to add users.%s column: %s", column_name, exc)
            refreshed = {
                col["name"] for col in inspect(sync_conn).get_columns(User.__tablename__)
            }
            if column_name not in refreshed:
                raise

    refreshed_inspector = inspect(sync_conn)
    final_columns = {
        column["name"] for column in refreshed_inspector.get_columns(User.__tablename__)
    }

    missing_after = _REQUIRED_USER_COLUMNS - final_columns
    if missing_after:
        raise RuntimeError(
            "users schema mismatch after ensure_columns: missing "
            + ", ".join(sorted(missing_after))
        )

    unique_constraints = refreshed_inspector.get_unique_constraints(User.__tablename__)
    has_unique_tg = any(
        constraint.get("column_names") == ["tg_id"] for constraint in unique_constraints
    )
    if not has_unique_tg:
        logger.info("[schema] users: creating unique index on tg_id")
        sync_conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tg_id ON users (tg_id)")
        )

    logger.info("[schema] users: final columns -> %s", sorted(final_columns))

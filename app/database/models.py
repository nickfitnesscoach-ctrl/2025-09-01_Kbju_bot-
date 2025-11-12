from datetime import datetime
import logging

from pathlib import Path

from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String, inspect, text
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url

try:  # pragma: no cover - совместимость разных версий SQLAlchemy
    from sqlalchemy.schema import AddColumn
except ImportError:  # pragma: no cover - fallback для SQLAlchemy 2.0+
    AddColumn = None  # type: ignore[assignment]

from config import DB_URL, DEBUG

logger = logging.getLogger(__name__)


def _ensure_sqlite_directory(db_url: str) -> None:
    """Create a directory for SQLite databases if it does not exist."""

    try:
        url = make_url(db_url)
    except Exception:  # noqa: BLE001 - keep engine creation resilient
        logger.warning("Failed to parse DB_URL, skipping SQLite directory check")
        return

    if url.get_backend_name() != "sqlite":
        return

    database: str | None = url.database
    if not database or database == ":memory:":
        return

    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # noqa: BLE001 - log but do not break import
        logger.error("Failed to create directory for SQLite database %s: %s", path, exc)


_ensure_sqlite_directory(DB_URL)

engine = create_async_engine(url=DB_URL, echo=DEBUG)

async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        Index('idx_funnel_status', 'funnel_status'),
        Index('idx_last_activity', 'last_activity_at'),
        Index('idx_calculated_at', 'calculated_at'),
    )

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

    # Новые поля для расширенного опроса
    target_weight: Mapped[float] = mapped_column(Float, nullable=True)
    current_body_type: Mapped[str] = mapped_column(String(10), nullable=True)  # "1", "2", "3", "4"
    target_body_type: Mapped[str] = mapped_column(String(10), nullable=True)   # "1", "2", "3", "4"
    timezone: Mapped[str] = mapped_column(String(50), nullable=True)           # "msk", "spb", etc.

    # AI-рекомендации
    ai_recommendations: Mapped[str] = mapped_column(String(4000), nullable=True)
    ai_generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Статусы воронки лидов
    funnel_status: Mapped[str] = mapped_column(String(20), default='new')  # new/calculated/hotlead
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


class BodyTypeImage(Base):
    """Telegram file_id для изображений типов фигур"""
    __tablename__ = 'body_type_images'

    id: Mapped[int] = mapped_column(primary_key=True)
    gender: Mapped[str] = mapped_column(String(10))        # "male" / "female"
    category: Mapped[str] = mapped_column(String(20))      # "current" / "target"
    type_number: Mapped[str] = mapped_column(String(5))    # "1", "2", "3", "4"
    file_id: Mapped[str] = mapped_column(String(200))      # Telegram file_id
    caption: Mapped[str] = mapped_column(String(200), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_body_image_unique', 'gender', 'category', 'type_number', unique=True),
    )


class BotSettings(Base):
    """Редактируемые настройки бота"""
    __tablename__ = 'bot_settings'

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(String(2000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


def _ensure_extended_survey_columns(sync_conn) -> None:
    """Добавить колонки для расширенного опроса"""
    inspector = inspect(sync_conn)
    existing = {column["name"] for column in inspector.get_columns(User.__tablename__)}

    new_columns = [
        ("target_weight", "ALTER TABLE users ADD COLUMN target_weight FLOAT"),
        ("current_body_type", "ALTER TABLE users ADD COLUMN current_body_type VARCHAR(10)"),
        ("target_body_type", "ALTER TABLE users ADD COLUMN target_body_type VARCHAR(10)"),
        ("timezone", "ALTER TABLE users ADD COLUMN timezone VARCHAR(50)"),
        ("ai_recommendations", "ALTER TABLE users ADD COLUMN ai_recommendations TEXT"),
        ("ai_generated_at", "ALTER TABLE users ADD COLUMN ai_generated_at DATETIME"),
    ]

    for col_name, sql in new_columns:
        if col_name not in existing:
            try:
                sync_conn.execute(text(sql))
                logger.info(f"Added column users.{col_name}")
            except SQLAlchemyError as exc:
                logger.exception(f"Failed to add column {col_name}: {exc}")
                raise


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_additional_user_columns)
        await conn.run_sync(_ensure_extended_survey_columns)


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
    _ensure_column(
        "updated_at",
        Column("updated_at", DateTime, nullable=True),
        "ALTER TABLE users ADD COLUMN updated_at DATETIME",
        "Adding users.updated_at column for tracking updates",
    )

    # Миграция для обновления NULL значений drip_stage
    if "drip_stage" in existing:
        try:
            sync_conn.execute(
                text("UPDATE users SET drip_stage = 0 WHERE drip_stage IS NULL")
            )
            logger.debug("Updated NULL drip_stage values to 0")
        except SQLAlchemyError as exc:
            logger.warning("Failed to update NULL drip_stage values: %s", exc)

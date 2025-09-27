from datetime import datetime
import logging

from pathlib import Path

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, inspect, text
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


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_additional_user_columns)


def _ensure_additional_user_columns(sync_conn) -> None:
    """Гарантировать наличие дополнительных колонок в таблице users."""

    _drop_legacy_priority_columns(sync_conn)

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


def _drop_legacy_priority_columns(sync_conn) -> None:
    """Удалить устаревшие колонки priority и priority_score из таблицы users."""

    inspector = inspect(sync_conn)
    columns = [column["name"] for column in inspector.get_columns(User.__tablename__)]
    legacy_columns = [column for column in ("priority", "priority_score") if column in columns]

    if not legacy_columns:
        logger.debug("No legacy priority columns present in users table")
        return

    if sync_conn.dialect.name != "sqlite":
        for column in legacy_columns:
            logger.info("Dropping legacy users.%s column", column)
            try:
                sync_conn.execute(text(f"ALTER TABLE {User.__tablename__} DROP COLUMN {column}"))
            except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to drop users.%s column: %s", column, exc)
                raise
        return

    logger.info("Recreating users table without legacy priority columns")

    sync_conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    success = False

    try:
        sync_conn.exec_driver_sql("BEGIN")
        sync_conn.exec_driver_sql(
            """
            CREATE TABLE users_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tg_id INTEGER NOT NULL UNIQUE,
              username TEXT,
              first_name TEXT,
              gender TEXT,
              age INTEGER,
              weight REAL,
              height INTEGER,
              activity TEXT,
              goal TEXT,
              calories INTEGER,
              proteins INTEGER,
              fats INTEGER,
              carbs INTEGER,
              funnel_status TEXT,
              hot_lead_notified_at TEXT,
              last_activity_at TEXT,
              drip_stage INTEGER DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              calculated_at TEXT
            )
            """
        )
        sync_conn.exec_driver_sql(
            """
            INSERT INTO users_new
              (id,tg_id,username,first_name,gender,age,weight,height,activity,goal,calories,proteins,fats,carbs,
               funnel_status,hot_lead_notified_at,last_activity_at,drip_stage,created_at,updated_at,calculated_at)
            SELECT
              id,tg_id,username,first_name,gender,age,weight,height,activity,goal,calories,proteins,fats,carbs,
              funnel_status,hot_lead_notified_at,last_activity_at,drip_stage,created_at,updated_at,calculated_at
            FROM users
            """
        )
        sync_conn.exec_driver_sql("DROP TABLE users")
        sync_conn.exec_driver_sql("ALTER TABLE users_new RENAME TO users")
        sync_conn.exec_driver_sql("COMMIT")
        success = True
    except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to recreate users table without legacy columns: %s", exc)
        try:
            sync_conn.exec_driver_sql("ROLLBACK")
        except SQLAlchemyError:
            logger.exception("Failed to rollback users table recreation")
        raise
    finally:
        sync_conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    if success:
        sync_conn.exec_driver_sql("VACUUM")

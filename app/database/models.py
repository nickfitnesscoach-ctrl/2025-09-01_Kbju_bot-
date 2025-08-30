from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DB_URL

engine = create_async_engine(url=DB_URL,
                             echo=True)
    
async_session = async_sessionmaker(engine)


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
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # для таймера


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

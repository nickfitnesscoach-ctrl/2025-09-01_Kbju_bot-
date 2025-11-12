# 🚀 Development Roadmap: КБЖУ Калькулятор → AI-тест

> **Статус проекта:** 🟡 В разработке
> **Начало:** 2025-01-12
> **Прогресс:** 0/10 модулей завершено

---

## 📊 Обзор проекта

### Текущая воронка → Новая воронка

```
❌ БЫЛО (6 вопросов):                    ✅ СТАНЕТ (10 вопросов + AI):
┌────────────────────┐                   ┌────────────────────┐
│ 1. Пол             │                   │ 1. Пол             │
│ 2. Возраст         │                   │ 2. Возраст         │
│ 3. Рост            │                   │ 3. Рост            │
│ 4. Вес             │                   │ 4. Вес текущий     │
│ 5. Активность      │                   │ 5. Вес желаемый    │🆕
│ 6. Цель            │                   │ 6. Фото: текущая   │🆕
│                    │                   │ 7. Фото: желаемая  │🆕
│                    │                   │ 8. Часовой пояс    │🆕
│                    │                   │ 9. Активность      │
│                    │                   │ 10. Цель           │
└────────────────────┘                   └────────────────────┘
         ↓                                        ↓
┌────────────────────┐                   ┌────────────────────┐
│ Расчет КБЖУ        │                   │ Проверка подписки  │🆕
│ → Конец            │                   └────────────────────┘
└────────────────────┘                            ↓
                                         ┌────────────────────┐
                                         │ Расчет КБЖУ        │
                                         └────────────────────┘
                                                  ↓
                                         ┌────────────────────┐
                                         │ AI-рекомендации    │🆕
                                         └────────────────────┘
                                                  ↓
                                         ┌────────────────────┐
                                         │ Оффер тренера      │🆕
                                         └────────────────────┘
                                                  ↓
                                         ┌────────────────────┐
                                         │ Drip-рассылка      │🆕
                                         │ (вкл/выкл)         │
                                         └────────────────────┘
```

### Новые возможности

✅ **Расширенный опрос**: 4 новых вопроса для точного профиля
✅ **Визуальный выбор**: Фото типов фигур (4 варианта)
✅ **AI-рекомендации**: Персональные советы через OpenRouter GPT-4 mini
✅ **Обязательная подписка**: Проверка перед показом AI
✅ **Гибкий оффер**: Редактируемый текст в админке
✅ **Управление Drip**: Включение/отключение рассылки
✅ **Админ-панель**: Загрузка фото, настройки, статистика

---

## 📦 Модули разработки

### Легенда статусов:
- ⬜ **Не начато**
- 🟡 **В работе**
- ✅ **Завершено**
- ⚠️ **Требует проверки**
- 🔴 **Заблокировано/Проблема**

---

## 📦 МОДУЛЬ 1: База данных и модели

**Статус:** ⬜ Не начато
**Приоритет:** 🔴 Критический (блокирует все остальное)
**Время:** ~4-6 часов
**Зависимости:** Нет

### Цель
Расширить базу данных для хранения новых данных: желаемый вес, типы фигур, часовой пояс, AI-рекомендации, изображения, настройки бота.

### Задачи

#### ☐ 1.1. Расширение модели User
**Файл:** `app/database/models.py`

**Добавить поля:**
```python
class User(Base):
    # ... существующие поля ...

    # 🆕 Новые поля для расширенного опроса
    target_weight: Mapped[float] = mapped_column(Float, nullable=True)
    current_body_type: Mapped[str] = mapped_column(String(10), nullable=True)  # "1", "2", "3", "4"
    target_body_type: Mapped[str] = mapped_column(String(10), nullable=True)   # "1", "2", "3", "4"
    timezone: Mapped[str] = mapped_column(String(50), nullable=True)           # "msk", "spb", etc.

    # 🆕 AI-рекомендации
    ai_recommendations: Mapped[str] = mapped_column(String(4000), nullable=True)
    ai_generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
```

**Чеклист:**
- [ ] Добавить поле `target_weight`
- [ ] Добавить поле `current_body_type`
- [ ] Добавить поле `target_body_type`
- [ ] Добавить поле `timezone`
- [ ] Добавить поле `ai_recommendations`
- [ ] Добавить поле `ai_generated_at`

---

#### ☐ 1.2. Создание таблицы BodyTypeImage
**Файл:** `app/database/models.py`

**Добавить класс:**
```python
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
```

**Чеклист:**
- [ ] Создать класс BodyTypeImage
- [ ] Добавить все поля
- [ ] Создать уникальный индекс

---

#### ☐ 1.3. Создание таблицы BotSettings
**Файл:** `app/database/models.py`

**Добавить класс:**
```python
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
```

**Чеклист:**
- [ ] Создать класс BotSettings
- [ ] Добавить все поля
- [ ] Добавить уникальный constraint на key

---

#### ☐ 1.4. Написание миграции
**Файл:** `app/database/models.py`

**Добавить функцию:**
```python
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
```

**Обновить async_main():**
```python
async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_additional_user_columns)
        await conn.run_sync(_ensure_extended_survey_columns)  # 🆕
```

**Чеклист:**
- [ ] Написать функцию _ensure_extended_survey_columns()
- [ ] Добавить вызов в async_main()
- [ ] Протестировать на существующей БД

---

#### ☐ 1.5. CRUD функции для новых таблиц
**Файл:** `app/database/requests.py`

**Добавить функции:**

```python
# ============= BodyTypeImage =============

async def get_body_type_image(
    gender: str,
    category: str,
    type_number: str
) -> BodyTypeImage | None:
    """Получить изображение типа фигуры"""
    async with async_session() as session:
        result = await session.execute(
            select(BodyTypeImage).where(
                BodyTypeImage.gender == gender,
                BodyTypeImage.category == category,
                BodyTypeImage.type_number == type_number
            )
        )
        return result.scalar_one_or_none()


async def get_body_type_images_by_category(
    gender: str,
    category: str
) -> list[BodyTypeImage]:
    """Получить все изображения для категории (current/target)"""
    async with async_session() as session:
        result = await session.execute(
            select(BodyTypeImage)
            .where(
                BodyTypeImage.gender == gender,
                BodyTypeImage.category == category
            )
            .order_by(BodyTypeImage.type_number)
        )
        return list(result.scalars().all())


async def save_body_type_image(
    gender: str,
    category: str,
    type_number: str,
    file_id: str,
    caption: str | None = None
) -> BodyTypeImage:
    """Сохранить или обновить изображение типа фигуры"""
    async with async_session() as session:
        # Проверяем, существует ли
        existing = await session.execute(
            select(BodyTypeImage).where(
                BodyTypeImage.gender == gender,
                BodyTypeImage.category == category,
                BodyTypeImage.type_number == type_number
            )
        )
        img = existing.scalar_one_or_none()

        if img:
            # Обновляем
            img.file_id = file_id
            img.caption = caption
            img.uploaded_at = datetime.utcnow()
        else:
            # Создаем новый
            img = BodyTypeImage(
                gender=gender,
                category=category,
                type_number=type_number,
                file_id=file_id,
                caption=caption
            )
            session.add(img)

        await session.commit()
        await session.refresh(img)
        return img


async def get_all_body_type_images() -> list[BodyTypeImage]:
    """Получить все изображения (для админки)"""
    async with async_session() as session:
        result = await session.execute(
            select(BodyTypeImage).order_by(
                BodyTypeImage.gender,
                BodyTypeImage.category,
                BodyTypeImage.type_number
            )
        )
        return list(result.scalars().all())


async def delete_body_type_image(image_id: int) -> bool:
    """Удалить изображение"""
    async with async_session() as session:
        img = await session.get(BodyTypeImage, image_id)
        if img:
            await session.delete(img)
            await session.commit()
            return True
        return False


# ============= BotSettings =============

async def get_setting(key: str) -> str | None:
    """Получить настройку бота"""
    async with async_session() as session:
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None


async def set_setting(key: str, value: str) -> None:
    """Установить настройку бота"""
    async with async_session() as session:
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = BotSettings(key=key, value=value)
            session.add(setting)

        await session.commit()


async def get_all_settings() -> dict[str, str]:
    """Получить все настройки"""
    async with async_session() as session:
        result = await session.execute(select(BotSettings))
        settings = result.scalars().all()
        return {s.key: s.value for s in settings}
```

**Чеклист:**
- [ ] Добавить get_body_type_image()
- [ ] Добавить get_body_type_images_by_category()
- [ ] Добавить save_body_type_image()
- [ ] Добавить get_all_body_type_images()
- [ ] Добавить delete_body_type_image()
- [ ] Добавить get_setting()
- [ ] Добавить set_setting()
- [ ] Добавить get_all_settings()

---

### ☐ 1.6. Тестирование миграции

**Команда:**
```bash
python -c "import asyncio; from app.database.models import async_main; asyncio.run(async_main())"
```

**Проверить:**
- [ ] Таблицы созданы без ошибок
- [ ] Новые колонки в users присутствуют
- [ ] Таблица body_type_images создана
- [ ] Таблица bot_settings создана
- [ ] Индексы созданы корректно
- [ ] Существующие данные не повреждены

---

### Критерии завершения модуля 1:
- ✅ Все таблицы и колонки созданы
- ✅ Миграция работает на существующей БД
- ✅ Все CRUD функции написаны
- ✅ Тесты пройдены

**Результат:** База данных готова для хранения новых данных

---

## 📦 МОДУЛЬ 2: FSM States и константы

**Статус:** ⬜ Не начато
**Приоритет:** 🟡 Высокий
**Время:** ~1 час
**Зависимости:** Нет

### Цель
Добавить новые состояния FSM для расширенного опроса и создать константы для часовых поясов и настроек.

### Задачи

#### ☐ 2.1. Добавление новых состояний
**Файл:** `app/states.py`

```python
from aiogram.fsm.state import State, StatesGroup

class KbjuForm(StatesGroup):
    # Существующие
    gender = State()
    age = State()
    weight = State()
    height = State()

    # 🆕 Новые состояния (после height, до activity)
    target_weight = State()
    current_body_type = State()
    target_body_type = State()
    timezone = State()

    # Существующие (продолжение)
    activity = State()
    goal = State()

    # 🆕 Проверка подписки (перед AI)
    checking_subscription = State()
```

**Чеклист:**
- [ ] Добавить state `target_weight`
- [ ] Добавить state `current_body_type`
- [ ] Добавить state `target_body_type`
- [ ] Добавить state `timezone`
- [ ] Добавить state `checking_subscription`

---

#### ☐ 2.2. Константы часовых поясов
**Файл:** `app/constants.py`

```python
# Часовые пояса России + Европа
TIMEZONES = {
    "msk": "🏛 Москва (МСК, UTC+3)",
    "spb": "🏰 Санкт-Петербург (МСК, UTC+3)",
    "kazan": "🕌 Казань (МСК, UTC+3)",
    "ufa": "🏔 Уфа (МСК, UTC+3)",
    "tyumen": "🌲 Тюмень (GMT+5)",
    "yekt": "🏭 Екатеринбург (GMT+5)",
    "nsk": "🌆 Новосибирск (GMT+7)",
    "kras": "🏞 Красноярск (GMT+7)",
    "irk": "🏔 Иркутск (GMT+8)",
    "vlad": "🌊 Владивосток (GMT+10)",
    "cet": "🇪🇺 Центральная Европа (CET, UTC+1)",
    "eet": "🇪🇺 Восточная Европа (EET, UTC+2)",
}

# Настройки бота (ключи для bot_settings)
SETTING_OFFER_TEXT = "offer_text"
SETTING_DRIP_ENABLED = "drip_enabled"

# Дефолтный текст оффера
DEFAULT_OFFER_TEXT = """
💪 Хочешь получить персональный план питания и тренировок?

📲 Напиши тренеру для консультации!
"""
```

**Чеклист:**
- [ ] Добавить словарь TIMEZONES
- [ ] Добавить SETTING_OFFER_TEXT
- [ ] Добавить SETTING_DRIP_ENABLED
- [ ] Добавить DEFAULT_OFFER_TEXT

---

#### ☐ 2.3. Тексты для новых вопросов
**Файл:** `app/texts.py` или `app/texts_data.json`

**Добавить тексты:**
```python
{
    # Новые вопросы
    "ask_target_weight": "Какой ваш желаемый вес? (укажите в кг)",
    "ask_current_body_type": "Выберите вашу текущую фигуру:",
    "ask_target_body_type": "Выберите желаемую фигуру:",
    "ask_timezone": "Выберите ваш часовой пояс:",

    # Валидация
    "invalid_weight": "Пожалуйста, введите корректный вес (число от 30 до 300 кг)",

    # Подписка
    "subscription_required": "Для получения AI-рекомендаций подпишитесь на наш канал:",
    "subscription_confirmed": "✅ Подписка подтверждена! Генерирую рекомендации...",
    "subscription_not_confirmed": "❌ Вы еще не подписались на канал",

    # AI
    "generating_ai": "⏳ Анализирую ваши данные и генерирую персональные рекомендации...",
    "ai_error": "Произошла ошибка при генерации рекомендаций. Попробуйте позже.",

    # КБЖУ результат
    "kbju_result": """
✅ Ваши рекомендации по КБЖУ:

🔥 Калории: {calories} ккал
🥩 Белки: {proteins} г
🥑 Жиры: {fats} г
🍞 Углеводы: {carbs} г
"""
}
```

**Чеклист:**
- [ ] Добавить тексты для новых вопросов
- [ ] Добавить тексты валидации
- [ ] Добавить тексты проверки подписки
- [ ] Добавить тексты для AI

---

### Критерии завершения модуля 2:
- ✅ Все состояния FSM добавлены
- ✅ Константы часовых поясов созданы
- ✅ Все тексты добавлены
- ✅ Импорты проверены

**Результат:** FSM и константы готовы для использования в handlers

---

## 📦 МОДУЛЬ 3: OpenRouter AI интеграция

**Статус:** ⬜ Не начато
**Приоритет:** 🔴 Критический
**Время:** ~2-3 часа
**Зависимости:** Модуль 1 (БД)

### Цель
Интегрировать OpenRouter API для генерации персонализированных AI-рекомендаций через GPT-4 mini.

### Задачи

#### ☐ 3.1. Конфигурация OpenRouter
**Файл:** `config.py`

```python
# OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = 'openai/gpt-4o-mini'
OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'

# ID канала для обязательной подписки
REQUIRED_CHANNEL_ID = os.getenv('REQUIRED_CHANNEL_ID', '')
REQUIRED_CHANNEL_URL = os.getenv('REQUIRED_CHANNEL_URL', '')
```

**Файл:** `.env`

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxx
REQUIRED_CHANNEL_ID=@your_channel_username
REQUIRED_CHANNEL_URL=https://t.me/your_channel
```

**Чеклист:**
- [ ] Добавить переменные в config.py
- [ ] Добавить переменные в .env
- [ ] Получить API ключ OpenRouter
- [ ] Протестировать подключение

---

#### ☐ 3.2. Создание сервиса AI
**Файл:** `app/services/__init__.py`

```python
# Пустой файл для создания пакета
```

**Файл:** `app/services/ai_recommendations.py`

```python
import aiohttp
import asyncio
import logging
from typing import Dict, Any

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_ENDPOINT

logger = logging.getLogger(__name__)


async def generate_ai_recommendations(user_data: Dict[str, Any]) -> str:
    """
    Генерирует персонализированные рекомендации через OpenRouter GPT-4 mini

    Args:
        user_data: Словарь с данными пользователя:
            - gender: "male" / "female"
            - age: int
            - weight: float
            - height: int
            - target_weight: float
            - current_body_type: str
            - target_body_type: str
            - timezone: str
            - activity: str
            - goal: str
            - calories: int
            - proteins: int
            - fats: int
            - carbs: int

    Returns:
        Текст рекомендаций в формате HTML

    Raises:
        ValueError: Если API ключ не настроен
        Exception: Если запрос к API не удался
    """

    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not configured")
        raise ValueError("OpenRouter API key not configured")

    # Формируем промпт
    prompt = _build_prompt(user_data)

    # Отправляем запрос
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Ты профессиональный фитнес-тренер и нутрициолог. Говори на 'ты'."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 1200,
        "temperature": 0.7,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                    raise Exception(f"OpenRouter API returned {resp.status}")

                data = await resp.json()

                if 'choices' not in data or not data['choices']:
                    logger.error(f"Invalid OpenRouter response: {data}")
                    raise Exception("Invalid response from OpenRouter")

                result = data['choices'][0]['message']['content']
                logger.info(f"AI recommendations generated (length: {len(result)})")
                return result

    except asyncio.TimeoutError:
        logger.error("OpenRouter API timeout")
        raise Exception("AI service timeout")
    except Exception as e:
        logger.exception(f"Failed to generate AI recommendations: {e}")
        raise


def _build_prompt(user_data: Dict[str, Any]) -> str:
    """Создать промпт для AI на основе данных пользователя"""

    gender_ru = "мужской" if user_data.get('gender') == 'male' else "женский"

    goal_map = {
        'weight_loss': 'Похудение',
        'weight_gain': 'Набор массы',
        'maintenance': 'Поддержание веса'
    }
    goal_ru = goal_map.get(user_data.get('goal', ''), user_data.get('goal', ''))

    activity_map = {
        'low': 'Низкая (сидячая работа)',
        'moderate': 'Средняя (легкие тренировки 1-3 раза в неделю)',
        'high': 'Высокая (интенсивные тренировки 4-5 раз в неделю)',
        'very_high': 'Очень высокая (ежедневные тренировки)'
    }
    activity_ru = activity_map.get(user_data.get('activity', ''), user_data.get('activity', ''))

    weight_diff = user_data.get('weight', 0) - user_data.get('target_weight', 0)

    prompt = f"""
Проанализируй данные клиента и дай персонализированный ответ.

📋 Данные клиента:
• Пол: {gender_ru}
• Возраст: {user_data.get('age')} лет
• Рост: {user_data.get('height')} см
• Текущий вес: {user_data.get('weight')} кг
• Желаемый вес: {user_data.get('target_weight')} кг
• Разница: {abs(weight_diff):.1f} кг {'(сбросить)' if weight_diff > 0 else '(набрать)'}
• Уровень активности: {activity_ru}
• Цель: {goal_ru}
• Текущий тип фигуры: тип {user_data.get('current_body_type')}
• Желаемый тип фигуры: тип {user_data.get('target_body_type')}
• Часовой пояс: {user_data.get('timezone')}

📊 Рассчитанные КБЖУ:
• Калории: {user_data.get('calories')} ккал/день
• Белки: {user_data.get('proteins')} г
• Жиры: {user_data.get('fats')} г
• Углеводы: {user_data.get('carbs')} г

---

Дай ответ СТРОГО в следующем формате (используй эмодзи и структуру):

📊 <b>Анализ текущего состояния</b>
[2-3 предложения: BMI, оценка веса, примерный процент жира, тип фигуры]

🎯 <b>Безопасные цели</b>
[Реалистичный срок достижения цели, темп снижения/набора веса в неделю с учетом безопасности]

🎨 <b>Ожидаемые изменения</b>
• [конкретное изменение 1]
• [конкретное изменение 2]
• [конкретное изменение 3]

🏋️ <b>Целевые тренировки</b>
• [частота тренировок в неделю]
• [тип нагрузок: силовые/кардио/интервалы/баланс]

🍽 <b>Рамки по питанию</b>
[Краткие принципы питания: дефицит/профицит калорий, распределение БЖУ, примеры продуктов.
Упомяни, что точные цифры индивидуальны и тренер должен погрузиться в ситуацию клиента]

---

⚠️ Важно:
- Будь кратким (до 800 символов)
- Используй ТОЛЬКО указанные секции с эмодзи
- Не добавляй дополнительные разделы
- Говори на "ты", по-русски
- Используй HTML-теги <b> для жирного текста
- НЕ используй markdown (**text**), только HTML
"""

    return prompt
```

**Чеклист:**
- [ ] Создать папку app/services/
- [ ] Создать __init__.py
- [ ] Создать ai_recommendations.py
- [ ] Написать функцию generate_ai_recommendations()
- [ ] Написать функцию _build_prompt()
- [ ] Добавить обработку ошибок
- [ ] Добавить логирование

---

#### ☐ 3.3. Тестирование AI сервиса

**Создать тестовый скрипт:** `test_ai.py`

```python
import asyncio
from app.services.ai_recommendations import generate_ai_recommendations

async def test_ai():
    user_data = {
        'gender': 'male',
        'age': 25,
        'weight': 85.0,
        'height': 180,
        'target_weight': 75.0,
        'current_body_type': '3',
        'target_body_type': '1',
        'timezone': 'msk',
        'activity': 'moderate',
        'goal': 'weight_loss',
        'calories': 2200,
        'proteins': 165,
        'fats': 73,
        'carbs': 220
    }

    try:
        result = await generate_ai_recommendations(user_data)
        print("✅ AI recommendations generated successfully!")
        print("\n" + "="*60)
        print(result)
        print("="*60)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_ai())
```

**Команда:**
```bash
python test_ai.py
```

**Чеклист:**
- [ ] Создать test_ai.py
- [ ] Запустить тест
- [ ] Проверить формат ответа
- [ ] Проверить использование HTML тегов
- [ ] Проверить длину ответа (<1000 символов)
- [ ] Проверить наличие всех секций

---

### Критерии завершения модуля 3:
- ✅ OpenRouter настроен
- ✅ Функция generate_ai_recommendations() работает
- ✅ Промпт генерирует правильный формат
- ✅ Обработка ошибок реализована
- ✅ Тест пройден успешно

**Результат:** AI-сервис готов к использованию в боте

---

## 📦 МОДУЛЬ 4: Handlers - Новые вопросы

**Статус:** ⬜ Не начато
**Приоритет:** 🟡 Высокий
**Время:** ~3-4 часа
**Зависимости:** Модуль 1 (БД), Модуль 2 (FSM)

### Цель
Добавить handlers для 4 новых вопросов: желаемый вес, текущая фигура (с фото), желаемая фигура (с фото), часовой пояс.

### Задачи

#### ☐ 4.1. Handler: Желаемый вес
**Файл:** `app/user/kbju.py`

**Модифицировать handler для height:**
```python
@router.message(KbjuForm.height)
async def process_height_and_ask_target_weight(message: types.Message, state: FSMContext):
    """Обработка роста и вопрос о желаемом весе"""

    try:
        height = int(message.text)
        if not (100 <= height <= 250):
            await message.answer("Пожалуйста, введите корректный рост (100-250 см)")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите рост числом (например: 175)")
        return

    await state.update_data(height=height)

    # 🆕 Спрашиваем желаемый вес
    from app.texts import get_text
    await message.answer(get_text("ask_target_weight"))
    await state.set_state(KbjuForm.target_weight)
```

**Добавить новый handler:**
```python
@router.message(KbjuForm.target_weight)
async def process_target_weight_and_show_current_body(
    message: types.Message,
    state: FSMContext
):
    """Обработка желаемого веса и показ текущих фигур"""

    try:
        target_weight = float(message.text.replace(',', '.'))
        if not (30 <= target_weight <= 300):
            from app.texts import get_text
            await message.answer(get_text("invalid_weight"))
            return
    except ValueError:
        from app.texts import get_text
        await message.answer(get_text("invalid_weight"))
        return

    await state.update_data(target_weight=target_weight)

    # Получаем пол пользователя
    data = await state.get_data()
    gender = data.get('gender')

    # Показываем фото текущих фигур
    await show_body_type_photos(message, state, gender, 'current')
```

**Чеклист:**
- [ ] Модифицировать handler для height
- [ ] Добавить handler для target_weight
- [ ] Добавить валидацию веса (30-300 кг)
- [ ] Обработать запятую в вводе (75,5 → 75.5)

---

#### ☐ 4.2. Handler: Текущая фигура (с фото)
**Файл:** `app/user/kbju.py`

**Добавить вспомогательную функцию:**
```python
async def show_body_type_photos(
    message: types.Message,
    state: FSMContext,
    gender: str,
    category: str
):
    """
    Показать фотографии типов фигур

    Args:
        message: Сообщение пользователя
        state: FSM контекст
        gender: "male" или "female"
        category: "current" или "target"
    """
    from app.database.requests import get_body_type_images_by_category
    from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
    from app.texts import get_text

    # Загружаем изображения из БД
    images = await get_body_type_images_by_category(gender, category)

    if not images:
        # Если фото еще не загружены, пропускаем
        await message.answer("⚠️ Изображения типов фигур пока не загружены администратором.")

        # Переходим к следующему вопросу
        if category == 'current':
            # Пропускаем target_body_type тоже
            await message.answer(get_text("ask_timezone"))
            await state.set_state(KbjuForm.timezone)
        else:
            await message.answer(get_text("ask_timezone"))
            await state.set_state(KbjuForm.timezone)
        return

    # Отправляем медиа-группу (до 4 фото)
    media_group = [
        InputMediaPhoto(
            media=img.file_id,
            caption=img.caption or f"Тип {img.type_number}"
        )
        for img in images[:4]
    ]

    await message.answer_media_group(media_group)

    # Кнопки выбора в один ряд
    callback_prefix = f"body_{category}_"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"{callback_prefix}1"),
            InlineKeyboardButton(text="2", callback_data=f"{callback_prefix}2"),
            InlineKeyboardButton(text="3", callback_data=f"{callback_prefix}3"),
            InlineKeyboardButton(text="4", callback_data=f"{callback_prefix}4"),
        ]
    ])

    question_key = "ask_current_body_type" if category == 'current' else "ask_target_body_type"
    await message.answer(get_text(question_key), reply_markup=keyboard)

    # Устанавливаем состояние
    if category == 'current':
        await state.set_state(KbjuForm.current_body_type)
    else:
        await state.set_state(KbjuForm.target_body_type)
```

**Добавить callback handler:**
```python
@router.callback_query(lambda c: c.data.startswith("body_current_"))
async def process_current_body_and_show_target(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработка выбора текущей фигуры и показ желаемых"""

    type_number = callback.data.split("_")[-1]  # "1", "2", "3", "4"
    await state.update_data(current_body_type=type_number)
    await callback.answer()

    # Получаем пол
    data = await state.get_data()
    gender = data.get('gender')

    # Показываем фото желаемых фигур
    await show_body_type_photos(callback.message, state, gender, 'target')
```

**Чеклист:**
- [ ] Создать функцию show_body_type_photos()
- [ ] Добавить handler для body_current_*
- [ ] Проверить отправку медиа-группы
- [ ] Проверить кнопки в один ряд
- [ ] Обработать случай, если фото не загружены

---

#### ☐ 4.3. Handler: Желаемая фигура (с фото)
**Файл:** `app/user/kbju.py`

```python
@router.callback_query(lambda c: c.data.startswith("body_target_"))
async def process_target_body_and_ask_timezone(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработка выбора желаемой фигуры и вопрос о часовом поясе"""

    type_number = callback.data.split("_")[-1]
    await state.update_data(target_body_type=type_number)
    await callback.answer()

    # Показываем часовые пояса
    from app.constants import TIMEZONES
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.texts import get_text

    # Создаем кнопки по 2 в ряд
    buttons = []
    row = []
    for code, name in TIMEZONES.items():
        # Убираем эмодзи и берем только название города
        city_name = name.split('(')[0].strip()
        row.append(InlineKeyboardButton(
            text=city_name,
            callback_data=f"tz_{code}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer(get_text("ask_timezone"), reply_markup=keyboard)
    await state.set_state(KbjuForm.timezone)
```

**Чеклист:**
- [ ] Добавить handler для body_target_*
- [ ] Сохранить выбор в state
- [ ] Перейти к вопросу о часовом поясе

---

#### ☐ 4.4. Handler: Часовой пояс
**Файл:** `app/user/kbju.py`

```python
@router.callback_query(lambda c: c.data.startswith("tz_"))
async def process_timezone_and_ask_activity(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработка часового пояса и переход к вопросу об активности"""

    timezone = callback.data.split("_")[1]
    await state.update_data(timezone=timezone)
    await callback.answer()

    # Переходим к вопросу об активности
    # ВАЖНО: Вызываем существующую функцию для вопроса об активности
    await ask_activity(callback.message, state)


# Нужно убедиться, что функция ask_activity существует
# Если её нет, создаем:
async def ask_activity(message: types.Message, state: FSMContext):
    """Задать вопрос об уровне активности"""
    from app.keyboards import get_activity_keyboard
    from app.texts import get_text

    await message.answer(
        get_text("ask_activity"),  # Должен существовать в текстах
        reply_markup=get_activity_keyboard()
    )
    await state.set_state(KbjuForm.activity)
```

**Чеклист:**
- [ ] Добавить handler для tz_*
- [ ] Сохранить timezone в state
- [ ] Перейти к вопросу об активности
- [ ] Проверить, что ask_activity() работает

---

### Критерии завершения модуля 4:
- ✅ Handler для желаемого веса работает
- ✅ Показ фото текущей фигуры работает
- ✅ Показ фото желаемой фигуры работает
- ✅ Выбор часового пояса работает
- ✅ Переход между вопросами корректный
- ✅ Обработка ошибок реализована

**Результат:** Расширенный опрос с 10 вопросами работает

---

## 📦 МОДУЛЬ 5: Проверка подписки на канал

**Статус:** ⬜ Не начато
**Приоритет:** 🟡 Высокий
**Время:** ~1-2 часа
**Зависимости:** Модуль 2 (FSM)

### Цель
Добавить обязательную проверку подписки на канал перед показом AI-рекомендаций.

### Задачи

#### ☐ 5.1. Функция проверки подписки
**Файл:** `app/user/kbju.py`

```python
from aiogram import Bot
from config import REQUIRED_CHANNEL_ID
import logging

logger = logging.getLogger(__name__)


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """
    Проверить подписку пользователя на канал

    Args:
        bot: Экземпляр бота
        user_id: Telegram ID пользователя

    Returns:
        True если подписан, False если нет
    """

    if not REQUIRED_CHANNEL_ID:
        logger.warning("REQUIRED_CHANNEL_ID not configured, skipping subscription check")
        return True

    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        is_subscribed = member.status in ["member", "administrator", "creator"]
        logger.debug(f"User {user_id} subscription status: {member.status}")
        return is_subscribed
    except Exception as e:
        logger.error(f"Failed to check subscription for user {user_id}: {e}")
        # В случае ошибки (например, бот не админ в канале) - пропускаем
        return False
```

**Чеклист:**
- [ ] Создать функцию check_subscription()
- [ ] Добавить логирование
- [ ] Обработать случай, если REQUIRED_CHANNEL_ID не настроен
- [ ] Обработать ошибку (бот не админ в канале)

---

#### ☐ 5.2. Модификация handler для goal
**Файл:** `app/user/kbju.py`

**Найти существующий handler для goal и заменить:**
```python
@router.callback_query(lambda c: c.data.startswith("goal_"), KbjuForm.goal)
async def process_goal_and_check_subscription(
    callback: types.CallbackQuery,
    state: FSMContext,
    bot: Bot
):
    """Обработка цели и проверка подписки перед расчетом"""

    goal = callback.data.split("_")[1]
    await state.update_data(goal=goal)
    await callback.answer()

    # 🆕 Проверяем подписку
    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if not is_subscribed:
        # Показываем кнопки подписки
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from config import REQUIRED_CHANNEL_URL
        from app.texts import get_text

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 Подписаться на канал",
                url=REQUIRED_CHANNEL_URL or "https://t.me/your_channel"
            )],
            [InlineKeyboardButton(
                text="✅ Проверить подписку",
                callback_data="check_subscription"
            )]
        ])

        await callback.message.answer(
            get_text("subscription_required"),
            reply_markup=keyboard
        )
        await state.set_state(KbjuForm.checking_subscription)
    else:
        # Сразу переходим к расчету
        await calculate_and_generate_ai(callback.message, state, bot, callback.from_user)
```

**Чеклист:**
- [ ] Найти handler для goal
- [ ] Добавить проверку подписки
- [ ] Показать кнопки, если не подписан
- [ ] Перейти к расчету, если подписан

---

#### ☐ 5.3. Handler для повторной проверки
**Файл:** `app/user/kbju.py`

```python
@router.callback_query(lambda c: c.data == "check_subscription")
async def recheck_subscription(
    callback: types.CallbackQuery,
    state: FSMContext,
    bot: Bot
):
    """Повторная проверка подписки после того, как пользователь подписался"""

    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if is_subscribed:
        from app.texts import get_text
        await callback.answer(get_text("subscription_confirmed"), show_alert=True)

        # Переходим к расчету
        await calculate_and_generate_ai(callback.message, state, bot, callback.from_user)
    else:
        from app.texts import get_text
        await callback.answer(get_text("subscription_not_confirmed"), show_alert=True)
```

**Чеклист:**
- [ ] Добавить handler для check_subscription
- [ ] Показать alert с результатом
- [ ] Перейти к расчету, если подписан
- [ ] Оставить в состоянии проверки, если не подписан

---

#### ☐ 5.4. Настройка канала

**Действия:**
1. Создать/выбрать канал в Telegram
2. Добавить бота в канал как администратора
3. Дать боту права: "Управление пользователями" (для проверки подписки)
4. Получить username канала (например: @your_fitness_channel)

**Обновить .env:**
```env
REQUIRED_CHANNEL_ID=@your_fitness_channel
REQUIRED_CHANNEL_URL=https://t.me/your_fitness_channel
```

**Чеклист:**
- [ ] Канал создан/выбран
- [ ] Бот добавлен как админ
- [ ] Права боту выданы
- [ ] .env обновлен с ID канала
- [ ] .env обновлен с URL канала

---

### Критерии завершения модуля 5:
- ✅ Функция check_subscription() работает
- ✅ Блокировка работает для не подписанных
- ✅ Повторная проверка работает
- ✅ Канал настроен
- ✅ Переход к расчету работает для подписанных

**Результат:** Обязательная подписка перед AI работает

---

## 📦 МОДУЛЬ 6: Расчет КБЖУ + AI + Оффер

**Статус:** ⬜ Не начато
**Приоритет:** 🔴 Критический
**Время:** ~2-3 часа
**Зависимости:** Модуль 1 (БД), Модуль 3 (AI)

### Цель
Объединить расчет КБЖУ, генерацию AI-рекомендаций и показ оффера в единый финальный флоу.

### Задачи

#### ☐ 6.1. Главная функция расчета и AI
**Файл:** `app/user/kbju.py`

```python
async def calculate_and_generate_ai(
    message: types.Message,
    state: FSMContext,
    bot: Bot,
    user: types.User
):
    """
    Расчет КБЖУ, генерация AI-рекомендаций и показ оффера

    Полный финальный флоу после прохождения опроса
    """
    from app.calculator import calculate_kbju
    from app.services.ai_recommendations import generate_ai_recommendations
    from app.database.requests import get_user, update_user
    from app.texts import get_text
    from datetime import datetime
    import logging

    logger = logging.getLogger(__name__)

    # 1. Получаем все данные из state
    data = await state.get_data()

    # 2. Рассчитываем КБЖУ (существующая функция)
    kbju = calculate_kbju(
        gender=data['gender'],
        age=data['age'],
        weight=data['weight'],
        height=data['height'],
        activity=data['activity'],
        goal=data['goal']
    )

    # 3. Сохраняем в БД
    db_user = await get_user(user.id)
    if db_user:
        db_user.target_weight = data.get('target_weight')
        db_user.current_body_type = data.get('current_body_type')
        db_user.target_body_type = data.get('target_body_type')
        db_user.timezone = data.get('timezone')
        db_user.calories = kbju['calories']
        db_user.proteins = kbju['proteins']
        db_user.fats = kbju['fats']
        db_user.carbs = kbju['carbs']
        db_user.calculated_at = datetime.utcnow()
        db_user.funnel_status = 'calculated'
        await update_user(db_user)

    # 4. Показываем КБЖУ
    await message.answer(
        get_text("kbju_result").format(
            calories=kbju['calories'],
            proteins=kbju['proteins'],
            fats=kbju['fats'],
            carbs=kbju['carbs']
        )
    )

    # 5. Генерируем AI-рекомендации
    await message.answer(get_text("generating_ai"))

    try:
        # Собираем все данные для AI
        full_data = {**data, **kbju}

        ai_text = await generate_ai_recommendations(full_data)

        # Сохраняем AI-рекомендации
        if db_user:
            db_user.ai_recommendations = ai_text
            db_user.ai_generated_at = datetime.utcnow()
            await update_user(db_user)

        # Показываем рекомендации
        await message.answer(
            f"🤖 <b>Персональные рекомендации:</b>\n\n{ai_text}",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception(f"Failed to generate AI recommendations: {e}")
        await message.answer(get_text("ai_error"))

    # 6. Показываем оффер
    await show_trainer_offer(message, bot)

    # 7. Отправляем в webhook (существующая функция)
    from app.webhook import send_lead
    if db_user:
        await send_lead(db_user, event="kbju_lead_calculated")

    # 8. Очищаем state
    await state.clear()
```

**Чеклист:**
- [ ] Создать функцию calculate_and_generate_ai()
- [ ] Интегрировать calculate_kbju()
- [ ] Сохранить все данные в БД
- [ ] Показать КБЖУ пользователю
- [ ] Вызвать generate_ai_recommendations()
- [ ] Сохранить AI-рекомендации в БД
- [ ] Показать AI-рекомендации пользователю
- [ ] Вызвать show_trainer_offer()
- [ ] Отправить в webhook
- [ ] Очистить state

---

#### ☐ 6.2. Функция показа оффера
**Файл:** `app/user/kbju.py`

```python
async def show_trainer_offer(message: types.Message, bot: Bot):
    """
    Показать оффер тренера с кнопкой "Написать тренеру"

    Args:
        message: Сообщение пользователя
        bot: Экземпляр бота
    """
    from app.database.requests import get_setting
    from app.constants import DEFAULT_OFFER_TEXT, SETTING_OFFER_TEXT
    from config import ADMIN_CHAT_ID
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import logging

    logger = logging.getLogger(__name__)

    # Получаем текст оффера из настроек (редактируемый в админке)
    offer_text = await get_setting(SETTING_OFFER_TEXT)
    if not offer_text:
        offer_text = DEFAULT_OFFER_TEXT

    # Получаем username админа/тренера для кнопки
    trainer_username = None
    if ADMIN_CHAT_ID:
        try:
            admin = await bot.get_chat(ADMIN_CHAT_ID)
            if hasattr(admin, 'username') and admin.username:
                trainer_username = admin.username
        except Exception as e:
            logger.warning(f"Failed to get admin username: {e}")

    # Создаем кнопку
    keyboard = None
    if trainer_username:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✉️ Написать тренеру",
                url=f"https://t.me/{trainer_username}"
            )]
        ])

    await message.answer(offer_text, reply_markup=keyboard, parse_mode="HTML")
```

**Чеклист:**
- [ ] Создать функцию show_trainer_offer()
- [ ] Получить текст из настроек
- [ ] Использовать дефолтный текст, если не настроен
- [ ] Получить username тренера
- [ ] Создать кнопку с ссылкой
- [ ] Показать оффер пользователю

---

#### ☐ 6.3. Установка дефолтного оффера

**Создать скрипт:** `scripts/init_default_settings.py`

```python
"""
Скрипт для инициализации дефолтных настроек в БД
"""
import asyncio
from app.database.requests import set_setting
from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED, DEFAULT_OFFER_TEXT


async def init_settings():
    """Установить дефолтные настройки"""

    # Дефолтный текст оффера
    await set_setting(SETTING_OFFER_TEXT, DEFAULT_OFFER_TEXT)
    print(f"✅ Set {SETTING_OFFER_TEXT}")

    # Drip включена по умолчанию
    await set_setting(SETTING_DRIP_ENABLED, "true")
    print(f"✅ Set {SETTING_DRIP_ENABLED} = true")

    print("\n✅ Default settings initialized!")


if __name__ == '__main__':
    asyncio.run(init_settings())
```

**Команда:**
```bash
python scripts/init_default_settings.py
```

**Чеклист:**
- [ ] Создать папку scripts/
- [ ] Создать init_default_settings.py
- [ ] Запустить скрипт
- [ ] Проверить настройки в БД

---

### Критерии завершения модуля 6:
- ✅ Функция calculate_and_generate_ai() работает
- ✅ КБЖУ рассчитывается правильно
- ✅ AI-рекомендации генерируются
- ✅ Все данные сохраняются в БД
- ✅ Оффер показывается с кнопкой
- ✅ Webhook отправляет данные
- ✅ State очищается

**Результат:** Полный флоу от опроса до оффера работает

---

## 📦 МОДУЛЬ 7: Управление Drip-рассылкой

**Статус:** ⬜ Не начато
**Приоритет:** 🟢 Средний
**Время:** ~30 минут
**Зависимости:** Модуль 1 (БД)

### Цель
Добавить возможность включения/отключения drip-рассылки через настройку в БД.

### Задачи

#### ☐ 7.1. Модификация drip сервиса
**Файл:** `app/drip_followups.py`

**Найти функцию `_process_batch()` и добавить в начало:**

```python
async def _process_batch(bot: Bot, batch: list[User]) -> None:
    """Обработать батч пользователей"""

    # 🆕 Проверяем, включена ли drip-рассылка
    from app.database.requests import get_setting
    from app.constants import SETTING_DRIP_ENABLED

    drip_enabled = await get_setting(SETTING_DRIP_ENABLED)
    if drip_enabled == "false":
        logger.info("Drip campaign is disabled, skipping batch processing")
        return

    # Остальная логика без изменений
    # ...
```

**Чеклист:**
- [ ] Найти функцию _process_batch()
- [ ] Добавить проверку настройки в начало
- [ ] Вернуть без обработки, если drip отключен
- [ ] Добавить логирование

---

#### ☐ 7.2. Тестирование

**Тест 1: Включить drip**
```sql
UPDATE bot_settings SET value = 'true' WHERE key = 'drip_enabled';
```
- [ ] Drip-рассылка работает

**Тест 2: Отключить drip**
```sql
UPDATE bot_settings SET value = 'false' WHERE key = 'drip_enabled';
```
- [ ] Drip-рассылка не работает
- [ ] В логах: "Drip campaign is disabled"

**Чеклист:**
- [ ] Протестировать включение
- [ ] Протестировать отключение
- [ ] Проверить логи

---

### Критерии завершения модуля 7:
- ✅ Проверка настройки drip_enabled работает
- ✅ При "false" рассылка не отправляется
- ✅ При "true" рассылка работает
- ✅ Логирование корректное

**Результат:** Drip-рассылкой можно управлять через БД

---

## 📦 МОДУЛЬ 8: Обновление Webhook

**Статус:** ⬜ Не начато
**Приоритет:** 🟢 Средний
**Время:** ~30 минут
**Зависимости:** Модуль 1 (БД)

### Цель
Добавить новые поля в webhook для отправки в n8n → Google Sheets.

### Задачи

#### ☐ 8.1. Обновление полей webhook
**Файл:** `app/webhook.py`

**Найти `_USER_FIELDS_DEFAULTS` и добавить:**

```python
_USER_FIELDS_DEFAULTS: Dict[str, Any] = {
    # Существующие поля
    "tg_id": 0,
    "username": "",
    "first_name": "",
    "gender": "",
    "age": 0,
    "weight": 0.0,
    "height": 0,
    "activity": "",
    "goal": "",
    "calories": 0,
    "proteins": 0,
    "fats": 0,
    "carbs": 0,
    "funnel_status": "",
    "created_at": None,
    "updated_at": None,
    "calculated_at": None,

    # 🆕 Новые поля
    "target_weight": 0.0,
    "current_body_type": "",
    "target_body_type": "",
    "timezone": "",
    "ai_recommendations": "",
    "ai_generated_at": None,
}
```

**Найти `_DATETIME_FIELDS` и добавить:**

```python
_DATETIME_FIELDS = {
    "created_at",
    "updated_at",
    "calculated_at",
    "ai_generated_at"  # 🆕
}
```

**Чеклист:**
- [ ] Добавить target_weight
- [ ] Добавить current_body_type
- [ ] Добавить target_body_type
- [ ] Добавить timezone
- [ ] Добавить ai_recommendations
- [ ] Добавить ai_generated_at
- [ ] Добавить ai_generated_at в _DATETIME_FIELDS

---

#### ☐ 8.2. Тестирование webhook

**Создать тестового пользователя с новыми полями:**
```python
test_user = {
    "tg_id": 999999,
    "username": "test_user",
    "first_name": "Test",
    "gender": "male",
    "age": 25,
    "weight": 85.0,
    "height": 180,
    "target_weight": 75.0,
    "current_body_type": "3",
    "target_body_type": "1",
    "timezone": "msk",
    "activity": "moderate",
    "goal": "weight_loss",
    "calories": 2200,
    "proteins": 165,
    "fats": 73,
    "carbs": 220,
    "ai_recommendations": "Test recommendations",
    "funnel_status": "calculated"
}
```

**Команда:**
```python
from app.webhook import send_lead
import asyncio

asyncio.run(send_lead(test_user, event="test"))
```

**Проверить в Google Sheets:**
- [ ] Все новые поля присутствуют
- [ ] Данные корректны
- [ ] Форматирование правильное

---

### Критерии завершения модуля 8:
- ✅ Новые поля добавлены в webhook
- ✅ Тест отправки прошел успешно
- ✅ Google Sheets получает все данные
- ✅ Форматирование datetime полей корректно

**Результат:** Webhook отправляет полный набор данных

---

## 📦 МОДУЛЬ 9: Админ-панель - Изображения

**Статус:** ⬜ Не начато
**Приоритет:** 🟡 Высокий
**Время:** ~2-3 часа
**Зависимости:** Модуль 1 (БД)

### Цель
Создать интерфейс для загрузки и управления изображениями типов фигур.

### Задачи

#### ☐ 9.1. Страница управления изображениями
**Файл:** `app/admin_panel.py`

**Добавить route:**

```python
@app.route('/body_images')
@login_required
def body_images_page():
    """Страница управления изображениями типов фигур"""
    import asyncio
    from app.database.requests import get_all_body_type_images

    images = asyncio.run(get_all_body_type_images())
    return render_template('body_images.html', images=images)
```

**Чеклист:**
- [ ] Добавить route /body_images
- [ ] Добавить @login_required
- [ ] Получить все изображения из БД
- [ ] Передать в шаблон

---

#### ☐ 9.2. Загрузка изображения
**Файл:** `app/admin_panel.py`

```python
@app.route('/upload_body_image', methods=['POST'])
@login_required
def upload_body_image():
    """Загрузка изображения фигуры через форму"""
    import asyncio
    from aiogram import Bot
    from config import TOKEN, ADMIN_CHAT_ID
    from app.database.requests import save_body_type_image

    gender = request.form.get('gender')
    category = request.form.get('category')
    type_number = request.form.get('type_number')
    caption = request.form.get('caption', '')
    file = request.files.get('file')

    if not all([gender, category, type_number, file]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Проверка типа файла
    allowed_extensions = {'png', 'jpg', 'jpeg', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[-1].lower()
    if file_ext not in allowed_extensions:
        return jsonify({'error': 'Invalid file type'}), 400

    bot = Bot(token=TOKEN)

    try:
        # Отправляем фото боту (админу) для получения file_id
        message = asyncio.run(bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=file,
            caption=f"Загружено: {gender} - {category} - тип {type_number}"
        ))

        file_id = message.photo[-1].file_id

        # Сохраняем в БД
        asyncio.run(save_body_type_image(
            gender=gender,
            category=category,
            type_number=type_number,
            file_id=file_id,
            caption=caption or None
        ))

        asyncio.run(bot.session.close())

        return jsonify({
            'success': True,
            'file_id': file_id,
            'message': 'Image uploaded successfully'
        })

    except Exception as e:
        logger.exception(f"Failed to upload body image: {e}")
        return jsonify({'error': str(e)}), 500
```

**Чеклист:**
- [ ] Добавить route /upload_body_image
- [ ] Проверить все обязательные поля
- [ ] Валидировать тип файла
- [ ] Отправить фото боту
- [ ] Получить file_id
- [ ] Сохранить в БД
- [ ] Вернуть JSON ответ

---

#### ☐ 9.3. Удаление изображения
**Файл:** `app/admin_panel.py`

```python
@app.route('/delete_body_image/<int:image_id>', methods=['POST'])
@login_required
def delete_body_image(image_id):
    """Удалить изображение из БД"""
    import asyncio
    from app.database.requests import delete_body_type_image

    success = asyncio.run(delete_body_type_image(image_id))

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Image not found'}), 404
```

**Чеклист:**
- [ ] Добавить route /delete_body_image/<id>
- [ ] Вызвать delete_body_type_image()
- [ ] Вернуть результат

---

#### ☐ 9.4. HTML шаблон
**Файл:** `templates/body_images.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <h2>Управление изображениями типов фигур</h2>
    <p class="text-muted">Загрузите 16 изображений: по 4 для каждой категории (мужчины/женщины × текущая/желаемая)</p>

    <!-- Форма загрузки -->
    <div class="card mt-3">
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">Загрузить новое изображение</h5>
        </div>
        <div class="card-body">
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="row">
                    <div class="col-md-3">
                        <label>Пол:</label>
                        <select name="gender" class="form-control" required>
                            <option value="">-- Выберите --</option>
                            <option value="male">Мужской</option>
                            <option value="female">Женский</option>
                        </select>
                    </div>

                    <div class="col-md-3">
                        <label>Категория:</label>
                        <select name="category" class="form-control" required>
                            <option value="">-- Выберите --</option>
                            <option value="current">Текущая фигура</option>
                            <option value="target">Желаемая фигура</option>
                        </select>
                    </div>

                    <div class="col-md-2">
                        <label>Тип (номер):</label>
                        <select name="type_number" class="form-control" required>
                            <option value="">-- Выберите --</option>
                            <option value="1">1</option>
                            <option value="2">2</option>
                            <option value="3">3</option>
                            <option value="4">4</option>
                        </select>
                    </div>

                    <div class="col-md-4">
                        <label>Подпись (опционально):</label>
                        <input type="text" name="caption" class="form-control"
                               placeholder="Например: Текущая форма (~20%)">
                    </div>
                </div>

                <div class="row mt-3">
                    <div class="col-md-8">
                        <label>Файл изображения:</label>
                        <input type="file" name="file" class="form-control"
                               accept="image/png,image/jpeg,image/jpg,image/webp" required>
                        <small class="form-text text-muted">Форматы: PNG, JPG, JPEG, WEBP</small>
                    </div>
                    <div class="col-md-4 d-flex align-items-end">
                        <button type="submit" class="btn btn-success btn-block">
                            📤 Загрузить
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <hr class="my-4">

    <!-- Список загруженных изображений -->
    <h3>Загруженные изображения ({{ images|length }}/16)</h3>

    {% if images %}
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead class="thead-dark">
                <tr>
                    <th>ID</th>
                    <th>Пол</th>
                    <th>Категория</th>
                    <th>Тип</th>
                    <th>Подпись</th>
                    <th>Загружено</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for img in images %}
                <tr id="image-{{ img.id }}">
                    <td>{{ img.id }}</td>
                    <td>
                        {% if img.gender == 'male' %}
                            👨 Мужской
                        {% else %}
                            👩 Женский
                        {% endif %}
                    </td>
                    <td>
                        {% if img.category == 'current' %}
                            📷 Текущая
                        {% else %}
                            🎯 Желаемая
                        {% endif %}
                    </td>
                    <td><span class="badge badge-primary">{{ img.type_number }}</span></td>
                    <td>{{ img.caption or '-' }}</td>
                    <td>{{ img.uploaded_at.strftime('%Y-%m-%d %H:%M') if img.uploaded_at else '-' }}</td>
                    <td>
                        <button class="btn btn-sm btn-danger"
                                onclick="deleteImage({{ img.id }})">
                            🗑 Удалить
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="alert alert-info">
        <strong>Изображения не загружены.</strong> Загрузите 16 изображений для корректной работы опроса.
    </div>
    {% endif %}
</div>

<script>
// Загрузка изображения
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ Загрузка...';

    try {
        const response = await fetch('/upload_body_image', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            alert('✅ Изображение успешно загружено!');
            location.reload();
        } else {
            alert('❌ Ошибка: ' + (result.error || 'Unknown error'));
            submitBtn.disabled = false;
            submitBtn.textContent = '📤 Загрузить';
        }
    } catch (error) {
        alert('❌ Ошибка загрузки: ' + error.message);
        submitBtn.disabled = false;
        submitBtn.textContent = '📤 Загрузить';
    }
});

// Удаление изображения
async function deleteImage(imageId) {
    if (!confirm('Удалить это изображение?')) return;

    try {
        const response = await fetch(`/delete_body_image/${imageId}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            document.getElementById(`image-${imageId}`).remove();
            alert('✅ Изображение удалено');
            location.reload();
        } else {
            alert('❌ Ошибка удаления');
        }
    } catch (error) {
        alert('❌ Ошибка: ' + error.message);
    }
}
</script>
{% endblock %}
```

**Чеклист:**
- [ ] Создать body_images.html
- [ ] Добавить форму загрузки
- [ ] Добавить таблицу изображений
- [ ] Добавить JavaScript для загрузки
- [ ] Добавить JavaScript для удаления
- [ ] Добавить стили

---

#### ☐ 9.5. Ссылка в меню админки
**Файл:** `templates/base.html` или главная страница админки

**Добавить пункт меню:**
```html
<nav>
    <ul>
        <li><a href="/">Главная</a></li>
        <li><a href="/body_images">📷 Изображения фигур</a></li> <!-- 🆕 -->
        <li><a href="/settings">⚙️ Настройки</a></li>
    </ul>
</nav>
```

**Чеклист:**
- [ ] Добавить ссылку в меню
- [ ] Проверить навигацию

---

### Критерии завершения модуля 9:
- ✅ Страница /body_images работает
- ✅ Загрузка изображений работает
- ✅ file_id получается корректно
- ✅ Изображения сохраняются в БД
- ✅ Удаление работает
- ✅ Интерфейс понятен и удобен

**Результат:** Админ может загружать изображения фигур

---

## 📦 МОДУЛЬ 10: Админ-панель - Настройки

**Статус:** ⬜ Не начато
**Приоритет:** 🟡 Высокий
**Время:** ~1-2 часа
**Зависимости:** Модуль 1 (БД)

### Цель
Создать интерфейс для редактирования текста оффера и управления drip-рассылкой.

### Задачи

#### ☐ 10.1. Страница настроек
**Файл:** `app/admin_panel.py`

```python
@app.route('/settings')
@login_required
def settings_page():
    """Страница настроек бота"""
    import asyncio
    from app.database.requests import get_setting
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED, DEFAULT_OFFER_TEXT

    offer_text = asyncio.run(get_setting(SETTING_OFFER_TEXT))
    if not offer_text:
        offer_text = DEFAULT_OFFER_TEXT

    drip_enabled = asyncio.run(get_setting(SETTING_DRIP_ENABLED))
    drip_enabled = drip_enabled != "false"

    return render_template('settings.html',
                         offer_text=offer_text,
                         drip_enabled=drip_enabled)
```

**Чеклист:**
- [ ] Добавить route /settings
- [ ] Получить текст оффера
- [ ] Получить статус drip
- [ ] Передать в шаблон

---

#### ☐ 10.2. Сохранение настроек
**Файл:** `app/admin_panel.py`

```python
@app.route('/save_settings', methods=['POST'])
@login_required
def save_settings():
    """Сохранение настроек бота"""
    import asyncio
    from app.database.requests import set_setting
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED
    from flask import flash, redirect, url_for

    offer_text = request.form.get('offer_text', '')
    drip_enabled = request.form.get('drip_enabled') == 'on'

    asyncio.run(set_setting(SETTING_OFFER_TEXT, offer_text))
    asyncio.run(set_setting(SETTING_DRIP_ENABLED, "true" if drip_enabled else "false"))

    flash('✅ Настройки успешно сохранены', 'success')
    return redirect(url_for('settings_page'))
```

**Чеклист:**
- [ ] Добавить route /save_settings
- [ ] Получить данные из формы
- [ ] Сохранить в БД
- [ ] Показать flash-сообщение
- [ ] Редирект обратно

---

#### ☐ 10.3. HTML шаблон настроек
**Файл:** `templates/settings.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <h2>Настройки бота</h2>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                        <span aria-hidden="true">&times;</span>
                    </button>
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <form method="POST" action="/save_settings">
        <!-- Текст оффера -->
        <div class="card mt-3">
            <div class="card-header bg-info text-white">
                <h5 class="mb-0">📝 Текст оффера</h5>
            </div>
            <div class="card-body">
                <label for="offer_text">Текст, который показывается после AI-рекомендаций:</label>
                <textarea name="offer_text" id="offer_text" class="form-control" rows="8" required>{{ offer_text }}</textarea>
                <small class="form-text text-muted">
                    Используйте HTML-теги для форматирования: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;a href="..."&gt;ссылка&lt;/a&gt;
                </small>

                <!-- Превью -->
                <div class="mt-3">
                    <strong>Превью:</strong>
                    <div class="border p-3 bg-light" id="preview" style="white-space: pre-wrap;"></div>
                </div>
            </div>
        </div>

        <!-- Drip-рассылка -->
        <div class="card mt-3">
            <div class="card-header bg-warning text-dark">
                <h5 class="mb-0">📧 Drip-рассылка</h5>
            </div>
            <div class="card-body">
                <div class="form-check form-switch">
                    <input type="checkbox" name="drip_enabled" class="form-check-input" id="drip_enabled"
                           {% if drip_enabled %}checked{% endif %}>
                    <label class="form-check-label" for="drip_enabled">
                        <strong>Включить автоматическую drip-рассылку</strong>
                    </label>
                </div>
                <small class="form-text text-muted mt-2">
                    Догоняющие сообщения лидам, которые не завершили опрос.
                    Отправляются автоматически через определенные интервалы.
                </small>

                <!-- Индикатор статуса -->
                <div class="mt-3">
                    <span class="badge" id="drip_status">
                        {% if drip_enabled %}
                            <span class="badge badge-success">✅ Включена</span>
                        {% else %}
                            <span class="badge badge-secondary">⛔ Отключена</span>
                        {% endif %}
                    </span>
                </div>
            </div>
        </div>

        <!-- Кнопка сохранения -->
        <div class="mt-4">
            <button type="submit" class="btn btn-primary btn-lg btn-block">
                💾 Сохранить настройки
            </button>
        </div>
    </form>
</div>

<script>
// Превью оффера
const textarea = document.getElementById('offer_text');
const preview = document.getElementById('preview');

function updatePreview() {
    preview.innerHTML = textarea.value;
}

textarea.addEventListener('input', updatePreview);
updatePreview();

// Обновление индикатора drip
const dripCheckbox = document.getElementById('drip_enabled');
const dripStatus = document.getElementById('drip_status');

dripCheckbox.addEventListener('change', () => {
    if (dripCheckbox.checked) {
        dripStatus.innerHTML = '<span class="badge badge-success">✅ Включена</span>';
    } else {
        dripStatus.innerHTML = '<span class="badge badge-secondary">⛔ Отключена</span>';
    }
});
</script>
{% endblock %}
```

**Чеклист:**
- [ ] Создать settings.html
- [ ] Добавить textarea для оффера
- [ ] Добавить превью оффера
- [ ] Добавить checkbox для drip
- [ ] Добавить индикатор статуса drip
- [ ] Добавить JavaScript для превью
- [ ] Добавить стили

---

#### ☐ 10.4. Обновление списка лидов (новые колонки)
**Файл:** `app/admin_panel.py`

**В функции отображения лидов обновить список колонок:**

```python
# Найти где определяются колонки для отображения
columns_to_show = [
    'id', 'tg_id', 'username', 'first_name',
    'gender', 'age', 'weight', 'height',
    'target_weight',        # 🆕
    'current_body_type',    # 🆕
    'target_body_type',     # 🆕
    'timezone',             # 🆕
    'activity', 'goal',
    'calories', 'proteins', 'fats', 'carbs',
    'funnel_status',
    'created_at', 'calculated_at',
    'ai_generated_at'       # 🆕
]
```

**Чеклист:**
- [ ] Найти функцию отображения лидов
- [ ] Добавить новые колонки в список
- [ ] Проверить отображение

---

#### ☐ 10.5. Просмотр AI-рекомендаций
**Файл:** `app/admin_panel.py`

```python
@app.route('/lead/<int:lead_id>/ai_recommendations')
@login_required
def view_ai_recommendations(lead_id):
    """Просмотр AI-рекомендаций для конкретного лида"""
    import asyncio
    from app.database.requests import get_user
    from flask import flash, redirect, url_for

    user = asyncio.run(get_user(lead_id))

    if not user:
        flash('Лид не найден', 'warning')
        return redirect(url_for('index'))

    if not user.ai_recommendations:
        flash('AI-рекомендации еще не сгенерированы для этого лида', 'info')
        return redirect(url_for('index'))

    return render_template('ai_recommendations.html', user=user)
```

**Файл:** `templates/ai_recommendations.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <h2>AI-рекомендации для {{ user.first_name }} (@{{ user.username }})</h2>

    <div class="card mt-3">
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">Информация о лиде</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <p><strong>Telegram ID:</strong> {{ user.tg_id }}</p>
                    <p><strong>Username:</strong> @{{ user.username or '-' }}</p>
                    <p><strong>Имя:</strong> {{ user.first_name or '-' }}</p>
                </div>
                <div class="col-md-6">
                    <p><strong>Возраст:</strong> {{ user.age }} лет</p>
                    <p><strong>Вес:</strong> {{ user.weight }} кг → {{ user.target_weight }} кг</p>
                    <p><strong>Рост:</strong> {{ user.height }} см</p>
                </div>
            </div>
        </div>
    </div>

    <div class="card mt-3">
        <div class="card-header bg-success text-white">
            <h5 class="mb-0">🤖 AI-рекомендации</h5>
        </div>
        <div class="card-body">
            <div class="ai-content">
                {{ user.ai_recommendations|safe }}
            </div>
            <hr>
            <p class="text-muted">
                <small>Сгенерировано: {{ user.ai_generated_at.strftime('%Y-%m-%d %H:%M:%S') if user.ai_generated_at else '-' }}</small>
            </p>
        </div>
    </div>

    <div class="mt-3">
        <a href="/" class="btn btn-secondary">← Назад к списку лидов</a>
    </div>
</div>

<style>
.ai-content {
    font-size: 1.1rem;
    line-height: 1.8;
    white-space: pre-wrap;
}
</style>
{% endblock %}
```

**Чеклист:**
- [ ] Добавить route /lead/<id>/ai_recommendations
- [ ] Создать ai_recommendations.html
- [ ] Добавить ссылку в списке лидов
- [ ] Проверить отображение HTML

---

### Критерии завершения модуля 10:
- ✅ Страница /settings работает
- ✅ Редактирование оффера работает
- ✅ Превью оффера работает
- ✅ Управление drip работает
- ✅ Новые колонки в списке лидов
- ✅ Просмотр AI-рекомендаций работает

**Результат:** Админ может управлять всеми настройками

---

## 🎯 Финальное тестирование

**Статус:** ⬜ Не начато
**Время:** ~2-3 часа

### Чеклист полного тестирования

#### ☐ End-to-End тест воронки

**Тест 1: Полное прохождение опроса (мужчина)**
- [ ] /start → Приветствие
- [ ] Пол → Мужской
- [ ] Возраст → 25
- [ ] Рост → 180
- [ ] Вес → 85
- [ ] Желаемый вес → 75
- [ ] Текущая фигура → Показ 4 фото
- [ ] Выбор текущей фигуры → Тип 3
- [ ] Желаемая фигура → Показ 4 фото
- [ ] Выбор желаемой фигуры → Тип 1
- [ ] Часовой пояс → Москва
- [ ] Активность → Средняя
- [ ] Цель → Похудение
- [ ] Проверка подписки → Блокировка (если не подписан)
- [ ] Подписка → Проверить подписку → Пропускает
- [ ] Расчет КБЖУ → Показывает результаты
- [ ] AI-рекомендации → Генерируются и показываются
- [ ] Оффер → Показывается с кнопкой

**Тест 2: Полное прохождение опроса (женщина)**
- [ ] Аналогичный тест с gender=female
- [ ] Проверить, что показываются женские фото фигур

**Тест 3: Валидация**
- [ ] Неверный возраст (0, 150) → Ошибка
- [ ] Неверный рост (50, 300) → Ошибка
- [ ] Неверный вес (20, 400) → Ошибка
- [ ] Неверный желаемый вес (20, 400) → Ошибка

---

#### ☐ Тест базы данных

- [ ] Все данные сохраняются в БД
- [ ] target_weight сохраняется
- [ ] current_body_type сохраняется
- [ ] target_body_type сохраняется
- [ ] timezone сохраняется
- [ ] ai_recommendations сохраняется
- [ ] ai_generated_at сохраняется
- [ ] funnel_status = "calculated"

---

#### ☐ Тест AI-рекомендаций

- [ ] API ключ работает
- [ ] Рекомендации генерируются
- [ ] Формат правильный (5 секций)
- [ ] HTML теги работают
- [ ] Длина адекватная (<1000 символов)
- [ ] Ошибки обрабатываются

---

#### ☐ Тест проверки подписки

- [ ] Блокировка работает для не подписанных
- [ ] Кнопка "Подписаться" ведет на канал
- [ ] Кнопка "Проверить подписку" работает
- [ ] Пропускает подписанных пользователей

---

#### ☐ Тест Webhook

- [ ] Данные отправляются в n8n
- [ ] Google Sheets обновляется
- [ ] Все новые поля присутствуют
- [ ] Форматирование корректно

---

#### ☐ Тест Drip-рассылки

- [ ] При drip_enabled="true" работает
- [ ] При drip_enabled="false" не работает
- [ ] Логирование корректное

---

#### ☐ Тест админ-панели

**Изображения:**
- [ ] Загрузка работает
- [ ] file_id получается
- [ ] Сохранение в БД работает
- [ ] Список отображается
- [ ] Удаление работает

**Настройки:**
- [ ] Редактирование оффера работает
- [ ] Превью оффера работает
- [ ] Управление drip работает
- [ ] Сохранение работает

**Список лидов:**
- [ ] Новые колонки отображаются
- [ ] Данные корректны
- [ ] Просмотр AI-рекомендаций работает

---

## 📊 Прогресс разработки

### Общий прогресс: 0/10 модулей

- ⬜ Модуль 1: База данных (0%)
- ⬜ Модуль 2: FSM и константы (0%)
- ⬜ Модуль 3: OpenRouter AI (0%)
- ⬜ Модуль 4: Handlers - Новые вопросы (0%)
- ⬜ Модуль 5: Проверка подписки (0%)
- ⬜ Модуль 6: Расчет + AI + Оффер (0%)
- ⬜ Модуль 7: Drip-рассылка (0%)
- ⬜ Модуль 8: Webhook (0%)
- ⬜ Модуль 9: Админ - Изображения (0%)
- ⬜ Модуль 10: Админ - Настройки (0%)

### Оценка времени: ~3-4 дня

**День 1:** Модули 1-3 (База, FSM, AI)
**День 2:** Модули 4-6 (Handlers, Подписка, Расчет)
**День 3:** Модули 7-10 (Drip, Webhook, Админка)
**День 4:** Тестирование и исправления

---

## 🚀 Готовы начать?

**Следующий шаг:** Модуль 1 - База данных

Скажи **"начать модуль 1"**, и я помогу с реализацией! 🎯

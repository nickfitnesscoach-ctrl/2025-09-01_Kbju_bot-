# План реализации: Обновление воронки КБЖУ бота

## 🎯 Цель
Превратить простой КБЖУ калькулятор в полноценный AI-тест с:
- Расширенным опросом (желаемый вес, фото фигур, часовой пояс)
- AI-рекомендациями через OpenRouter (GPT-4 mini)
- Обязательной подпиской на канал перед AI
- Редактируемым оффером
- Управляемой drip-рассылкой

## 📊 Текущая воронка vs Новая воронка

### ❌ Сейчас (6 вопросов):
```
1. Пол
2. Возраст
3. Рост
4. Вес
5. Активность
6. Цель
   ↓
Расчет КBЖУ → Конец
```

### ✅ Новая воронка (10 вопросов + AI):
```
1. Пол
2. Возраст
3. Рост
4. Вес текущий
5. Вес желаемый           🆕
6. Текущая фигура (4 фото) 🆕
7. Желаемая фигура (4 фото) 🆕
8. Часовой пояс           🆕
9. Активность
10. Цель
    ↓
Проверка подписки 🆕
    ↓
Расчет КБЖУ
    ↓
AI-рекомендации 🆕
    ↓
Оффер тренера 🆕
    ↓
Drip-рассылка (вкл/выкл) 🆕
```

---

## 📋 План реализации (10 этапов)

### ✅ Этап 1: База данных (1 день)

**Файлы для изменения:**
- `app/database/models.py`

**Задачи:**

**1.1. Добавить новые поля в модель User**

```python
# app/database/models.py

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

**1.2. Создать таблицу для изображений фигур**

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

**1.3. Создать таблицу для настроек бота**

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

**1.4. Добавить миграцию**

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

# Вызвать в async_main()
async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_additional_user_columns)
        await conn.run_sync(_ensure_extended_survey_columns)  # 🆕
```

**1.5. Добавить функции в database/requests.py**

```python
# app/database/requests.py

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
```

**Чеклист Этап 1:**
- [ ] Добавить новые поля в User
- [ ] Создать BodyTypeImage модель
- [ ] Создать BotSettings модель
- [ ] Написать миграцию _ensure_extended_survey_columns()
- [ ] Добавить функции в requests.py
- [ ] Протестировать создание таблиц: `python -c "import asyncio; from app.database.models import async_main; asyncio.run(async_main())"`

---

### ✅ Этап 2: FSM States (30 минут)

**Файлы для изменения:**
- `app/states.py`

**Задачи:**

```python
# app/states.py

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

**Чеклист Этап 2:**
- [ ] Добавить новые состояния в KbjuForm
- [ ] Проверить импорты

---

### ✅ Этап 3: Константы и тексты (30 минут)

**Файлы для изменения:**
- `app/constants.py`
- `app/texts_data.json` (или `app/texts.py`)

**Задачи:**

**3.1. Добавить константы**

```python
# app/constants.py

# Часовые пояса
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

**3.2. Добавить тексты**

```python
# app/texts.py или texts_data.json

{
    "ask_target_weight": "Какой ваш желаемый вес? (укажите в кг)",
    "ask_current_body_type": "Выберите вашу текущую фигуру:",
    "ask_target_body_type": "Выберите желаемую фигуру:",
    "ask_timezone": "Выберите ваш часовой пояс:",

    "subscription_required": "Для получения AI-рекомендаций подпишитесь на наш канал:",
    "subscription_confirmed": "✅ Подписка подтверждена! Генерирую рекомендации...",
    "subscription_not_confirmed": "❌ Вы еще не подписались на канал",

    "generating_ai": "⏳ Анализирую ваши данные и генерирую персональные рекомендации...",
    "ai_error": "Произошла ошибка при генерации рекомендаций. Попробуйте позже.",

    "kbju_result": """
✅ Ваши рекомендации по КБЖУ:

🔥 Калории: {calories} ккал
🥩 Белки: {proteins} г
🥑 Жиры: {fats} г
🍞 Углеводы: {carbs} г
""",

    "invalid_weight": "Пожалуйста, введите корректный вес (число от 30 до 300 кг)"
}
```

**Чеклист Этап 3:**
- [ ] Добавить TIMEZONES в constants.py
- [ ] Добавить тексты для новых вопросов
- [ ] Добавить тексты для проверки подписки
- [ ] Добавить DEFAULT_OFFER_TEXT

---

### ✅ Этап 4: OpenRouter AI (1-2 часа)

**Файлы для создания:**
- `app/services/__init__.py`
- `app/services/ai_recommendations.py`

**Задачи:**

**4.1. Конфигурация**

```python
# config.py

# OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = 'openai/gpt-4o-mini'
OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'

# ID канала для обязательной подписки
REQUIRED_CHANNEL_ID = os.getenv('REQUIRED_CHANNEL_ID', '')
REQUIRED_CHANNEL_URL = os.getenv('REQUIRED_CHANNEL_URL', '')
```

**4.2. Сервис AI**

```python
# app/services/ai_recommendations.py

import aiohttp
import logging
from typing import Dict, Any

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_ENDPOINT

logger = logging.getLogger(__name__)


async def generate_ai_recommendations(user_data: Dict[str, Any]) -> str:
    """
    Генерирует персонализированные рекомендации через OpenRouter GPT-4 mini

    Args:
        user_data: Словарь с данными пользователя (gender, age, weight, etc.)

    Returns:
        Текст рекомендаций в формате markdown
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
                logger.info(f"AI recommendations generated for user (length: {len(result)})")
                return result

    except asyncio.TimeoutError:
        logger.error("OpenRouter API timeout")
        raise Exception("AI service timeout")
    except Exception as e:
        logger.exception(f"Failed to generate AI recommendations: {e}")
        raise


def _build_prompt(user_data: Dict[str, Any]) -> str:
    """Создать промпт для AI"""

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
• Текущий тип фигуры: {user_data.get('current_body_type')}
• Желаемый тип фигуры: {user_data.get('target_body_type')}
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

**4.3. Добавить в .env**

```env
# .env

OPENROUTER_API_KEY=sk-or-v1-xxxxx
REQUIRED_CHANNEL_ID=@your_channel_username
REQUIRED_CHANNEL_URL=https://t.me/your_channel
```

**Чеклист Этап 4:**
- [ ] Добавить конфиг в config.py
- [ ] Создать app/services/ai_recommendations.py
- [ ] Написать generate_ai_recommendations()
- [ ] Добавить переменные в .env
- [ ] Протестировать: `python -c "import asyncio; from app.services.ai_recommendations import generate_ai_recommendations; print(asyncio.run(generate_ai_recommendations({...})))"`

---

### ✅ Этап 5: Handlers - Новые вопросы (2-3 часа)

**Файлы для изменения:**
- `app/user/kbju.py`

**Задачи:**

**5.1. Добавить handler для желаемого веса**

```python
# app/user/kbju.py

# После handler'а для height:

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
    await message.answer(get_text("ask_target_weight"))
    await state.set_state(KbjuForm.target_weight)


@router.message(KbjuForm.target_weight)
async def process_target_weight_and_show_current_body(
    message: types.Message,
    state: FSMContext
):
    """Обработка желаемого веса и показ текущих фигур"""

    try:
        target_weight = float(message.text.replace(',', '.'))
        if not (30 <= target_weight <= 300):
            await message.answer(get_text("invalid_weight"))
            return
    except ValueError:
        await message.answer(get_text("invalid_weight"))
        return

    await state.update_data(target_weight=target_weight)

    # Получаем пол пользователя
    data = await state.get_data()
    gender = data.get('gender')

    # Загружаем изображения текущих фигур
    from app.database.requests import get_body_type_images_by_category
    from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

    images = await get_body_type_images_by_category(gender, 'current')

    if not images:
        # Если фото еще не загружены, пропускаем
        await message.answer("⚠️ Изображения типов фигур пока не загружены администратором.")
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="body_current_1"),
            InlineKeyboardButton(text="2", callback_data="body_current_2"),
            InlineKeyboardButton(text="3", callback_data="body_current_3"),
            InlineKeyboardButton(text="4", callback_data="body_current_4"),
        ]
    ])

    await message.answer(get_text("ask_current_body_type"), reply_markup=keyboard)
    await state.set_state(KbjuForm.current_body_type)
```

**5.2. Handler для текущей фигуры**

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

    # Загружаем изображения желаемых фигур
    from app.database.requests import get_body_type_images_by_category
    from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

    images = await get_body_type_images_by_category(gender, 'target')

    if not images:
        await callback.message.answer(get_text("ask_timezone"))
        await state.set_state(KbjuForm.timezone)
        return

    # Отправляем медиа-группу
    media_group = [
        InputMediaPhoto(
            media=img.file_id,
            caption=img.caption or f"Тип {img.type_number}"
        )
        for img in images[:4]
    ]

    await callback.message.answer_media_group(media_group)

    # Кнопки выбора
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="body_target_1"),
            InlineKeyboardButton(text="2", callback_data="body_target_2"),
            InlineKeyboardButton(text="3", callback_data="body_target_3"),
            InlineKeyboardButton(text="4", callback_data="body_target_4"),
        ]
    ])

    await callback.message.answer(get_text("ask_target_body_type"), reply_markup=keyboard)
    await state.set_state(KbjuForm.target_body_type)
```

**5.3. Handler для желаемой фигуры**

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

    # Создаем кнопки по 2 в ряд
    buttons = []
    row = []
    for code, name in TIMEZONES.items():
        row.append(InlineKeyboardButton(
            text=name.split('(')[0].strip(),  # Только название города
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

**5.4. Handler для часового пояса**

```python
@router.callback_query(lambda c: c.data.startswith("tz_"))
async def process_timezone_and_ask_activity(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработка часового пояса и вопрос об активности"""

    timezone = callback.data.split("_")[1]
    await state.update_data(timezone=timezone)
    await callback.answer()

    # Переходим к вопросу об активности (существующий handler)
    await ask_activity(callback.message, state)  # Вызываем существующую функцию
```

**Чеклист Этап 5:**
- [ ] Добавить handler для target_weight
- [ ] Добавить handler для current_body_type (с фото)
- [ ] Добавить handler для target_body_type (с фото)
- [ ] Добавить handler для timezone
- [ ] Протестировать локально прохождение опроса

---

### ✅ Этап 6: Проверка подписки (1 час)

**Файлы для изменения:**
- `app/user/kbju.py`

**Задачи:**

```python
# app/user/kbju.py

from aiogram import Bot
from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверить подписку пользователя на канал"""

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
        return False


# Модифицируем handler после выбора цели:

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

    # Проверяем подписку
    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if not is_subscribed:
        # Показываем кнопки подписки
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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


@router.callback_query(lambda c: c.data == "check_subscription")
async def recheck_subscription(
    callback: types.CallbackQuery,
    state: FSMContext,
    bot: Bot
):
    """Повторная проверка подписки"""

    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if is_subscribed:
        await callback.answer(get_text("subscription_confirmed"), show_alert=True)
        await calculate_and_generate_ai(callback.message, state, bot, callback.from_user)
    else:
        await callback.answer(get_text("subscription_not_confirmed"), show_alert=True)
```

**Чеклист Этап 6:**
- [ ] Добавить функцию check_subscription()
- [ ] Модифицировать handler для goal
- [ ] Добавить handler для recheck_subscription
- [ ] Протестировать с реальным каналом

---

### ✅ Этап 7: Расчет + AI + Оффер (2 часа)

**Файлы для изменения:**
- `app/user/kbju.py`

**Задачи:**

```python
# app/user/kbju.py

async def calculate_and_generate_ai(
    message: types.Message,
    state: FSMContext,
    bot: Bot,
    user: types.User
):
    """Расчет КБЖУ, генерация AI-рекомендаций и показ оффера"""

    from app.calculator import calculate_kbju
    from app.services.ai_recommendations import generate_ai_recommendations
    from app.database.requests import get_user, update_user, set_setting, get_setting
    from app.constants import DEFAULT_OFFER_TEXT, SETTING_OFFER_TEXT
    from datetime import datetime

    # 1. Получаем все данные
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

    # 4. Показываем КBЖУ
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
    await send_lead(db_user, event="kbju_lead_calculated")

    # 8. Очищаем state
    await state.clear()


async def show_trainer_offer(message: types.Message, bot: Bot):
    """Показать оффер тренера с кнопкой"""

    from app.database.requests import get_setting
    from app.constants import DEFAULT_OFFER_TEXT, SETTING_OFFER_TEXT
    from config import ADMIN_CHAT_ID
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # Получаем текст оффера из настроек
    offer_text = await get_setting(SETTING_OFFER_TEXT)
    if not offer_text:
        offer_text = DEFAULT_OFFER_TEXT

    # Получаем username админа/тренера
    if ADMIN_CHAT_ID:
        try:
            admin = await bot.get_chat(ADMIN_CHAT_ID)
            trainer_username = admin.username if hasattr(admin, 'username') else None
        except:
            trainer_username = None
    else:
        trainer_username = None

    # Создаем кнопку
    if trainer_username:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✉️ Написать тренеру",
                url=f"https://t.me/{trainer_username}"
            )]
        ])
    else:
        keyboard = None

    await message.answer(offer_text, reply_markup=keyboard)
```

**Чеклист Этап 7:**
- [ ] Создать функцию calculate_and_generate_ai()
- [ ] Создать функцию show_trainer_offer()
- [ ] Интегрировать с существующим webhook
- [ ] Протестировать полный флоу с AI
- [ ] Проверить сохранение в БД

---

### ✅ Этап 8: Управление Drip-рассылкой (30 минут)

**Файлы для изменения:**
- `app/drip_followups.py`

**Задачи:**

```python
# app/drip_followups.py

# В начале функции _process_batch() добавить проверку:

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

**Чеклист Этап 8:**
- [ ] Добавить проверку настройки drip_enabled
- [ ] Протестировать включение/отключение

---

### ✅ Этап 9: Админ-панель (3-4 часа)

**Файлы для изменения:**
- `app/admin_panel.py`

**Задачи:**

**9.1. Добавить страницу загрузки изображений**

```python
# app/admin_panel.py

@app.route('/body_images')
@login_required
def body_images_page():
    """Страница управления изображениями типов фигур"""
    import asyncio
    from app.database.requests import get_all_body_type_images

    images = asyncio.run(get_all_body_type_images())
    return render_template('body_images.html', images=images)


@app.route('/upload_body_image', methods=['POST'])
@login_required
def upload_body_image():
    """Загрузка изображения фигуры"""
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

    # Отправляем фото боту для получения file_id
    bot = Bot(token=TOKEN)

    try:
        # Отправляем фото админу
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
            caption=caption
        ))

        asyncio.run(bot.session.close())

        return jsonify({'success': True, 'file_id': file_id})

    except Exception as e:
        logger.exception(f"Failed to upload body image: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/delete_body_image/<int:image_id>', methods=['POST'])
@login_required
def delete_body_image(image_id):
    """Удалить изображение"""
    import asyncio
    from app.database.requests import async_session
    from app.database.models import BodyTypeImage

    async def delete_img():
        async with async_session() as session:
            img = await session.get(BodyTypeImage, image_id)
            if img:
                await session.delete(img)
                await session.commit()
                return True
            return False

    success = asyncio.run(delete_img())

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Image not found'}), 404
```

**9.2. Создать HTML шаблон для загрузки изображений**

```html
<!-- templates/body_images.html -->

{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <h2>Управление изображениями типов фигур</h2>

    <div class="card mt-3">
        <div class="card-header">
            <h5>Загрузить новое изображение</h5>
        </div>
        <div class="card-body">
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="row">
                    <div class="col-md-3">
                        <label>Пол:</label>
                        <select name="gender" class="form-control" required>
                            <option value="male">Мужской</option>
                            <option value="female">Женский</option>
                        </select>
                    </div>

                    <div class="col-md-3">
                        <label>Категория:</label>
                        <select name="category" class="form-control" required>
                            <option value="current">Текущая фигура</option>
                            <option value="target">Желаемая фигура</option>
                        </select>
                    </div>

                    <div class="col-md-2">
                        <label>Тип (номер):</label>
                        <select name="type_number" class="form-control" required>
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
                               accept="image/*" required>
                    </div>
                    <div class="col-md-4">
                        <label>&nbsp;</label>
                        <button type="submit" class="btn btn-primary btn-block">
                            Загрузить
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <hr class="my-4">

    <h3>Загруженные изображения</h3>

    <table class="table table-striped">
        <thead>
            <tr>
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
                <td>{{ 'Мужской' if img.gender == 'male' else 'Женский' }}</td>
                <td>{{ 'Текущая' if img.category == 'current' else 'Желаемая' }}</td>
                <td>{{ img.type_number }}</td>
                <td>{{ img.caption or '-' }}</td>
                <td>{{ img.uploaded_at.strftime('%Y-%m-%d %H:%M') }}</td>
                <td>
                    <button class="btn btn-sm btn-danger"
                            onclick="deleteImage({{ img.id }})">
                        Удалить
                    </button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<script>
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);

    try {
        const response = await fetch('/upload_body_image', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            alert('Изображение успешно загружено!');
            location.reload();
        } else {
            alert('Ошибка: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Ошибка загрузки: ' + error.message);
    }
});

async function deleteImage(imageId) {
    if (!confirm('Удалить изображение?')) return;

    try {
        const response = await fetch(`/delete_body_image/${imageId}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            document.getElementById(`image-${imageId}`).remove();
        } else {
            alert('Ошибка удаления');
        }
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}
</script>
{% endblock %}
```

**9.3. Добавить страницу настроек**

```python
# app/admin_panel.py

@app.route('/settings')
@login_required
def settings_page():
    """Страница настроек бота"""
    import asyncio
    from app.database.requests import get_setting
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED

    offer_text = asyncio.run(get_setting(SETTING_OFFER_TEXT)) or ""
    drip_enabled = asyncio.run(get_setting(SETTING_DRIP_ENABLED)) != "false"

    return render_template('settings.html',
                         offer_text=offer_text,
                         drip_enabled=drip_enabled)


@app.route('/save_settings', methods=['POST'])
@login_required
def save_settings():
    """Сохранение настроек"""
    import asyncio
    from app.database.requests import set_setting
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED

    offer_text = request.form.get('offer_text', '')
    drip_enabled = request.form.get('drip_enabled') == 'on'

    asyncio.run(set_setting(SETTING_OFFER_TEXT, offer_text))
    asyncio.run(set_setting(SETTING_DRIP_ENABLED, "true" if drip_enabled else "false"))

    flash('Настройки сохранены', 'success')
    return redirect(url_for('settings_page'))
```

**9.4. HTML шаблон настроек**

```html
<!-- templates/settings.html -->

{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <h2>Настройки бота</h2>

    <form method="POST" action="/save_settings">
        <div class="card mt-3">
            <div class="card-header">
                <h5>Текст оффера</h5>
            </div>
            <div class="card-body">
                <label>Текст, который показывается после AI-рекомендаций:</label>
                <textarea name="offer_text" class="form-control" rows="5">{{ offer_text }}</textarea>
                <small class="form-text text-muted">
                    Используйте HTML-теги для форматирования
                </small>
            </div>
        </div>

        <div class="card mt-3">
            <div class="card-header">
                <h5>Drip-рассылка</h5>
            </div>
            <div class="card-body">
                <div class="form-check">
                    <input type="checkbox" name="drip_enabled" class="form-check-input"
                           id="drip_enabled" {% if drip_enabled %}checked{% endif %}>
                    <label class="form-check-label" for="drip_enabled">
                        Включить автоматическую drip-рассылку
                    </label>
                </div>
                <small class="form-text text-muted">
                    Догоняющие сообщения лидам, которые не завершили опрос
                </small>
            </div>
        </div>

        <button type="submit" class="btn btn-primary mt-3">
            Сохранить настройки
        </button>
    </form>
</div>
{% endblock %}
```

**9.5. Обновить список лидов (добавить новые колонки)**

```python
# app/admin_panel.py

# В функции отображения лидов добавить колонки:

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

**9.6. Добавить просмотр AI-рекомендаций**

```python
@app.route('/lead/<int:lead_id>/ai_recommendations')
@login_required
def view_ai_recommendations(lead_id):
    """Просмотр AI-рекомендаций для лида"""
    import asyncio
    from app.database.requests import get_user

    user = asyncio.run(get_user(lead_id))

    if not user or not user.ai_recommendations:
        flash('Рекомендации не найдены', 'warning')
        return redirect(url_for('index'))

    return render_template('ai_recommendations.html', user=user)
```

**Чеклист Этап 9:**
- [ ] Создать страницу /body_images
- [ ] Создать HTML шаблон body_images.html
- [ ] Реализовать загрузку изображений через форму
- [ ] Создать страницу /settings
- [ ] Создать HTML шаблон settings.html
- [ ] Добавить новые колонки в список лидов
- [ ] Создать просмотр AI-рекомендаций
- [ ] Протестировать все функции админки

---

### ✅ Этап 10: Webhook обновление (30 минут)

**Файлы для изменения:**
- `app/webhook.py`

**Задачи:**

```python
# app/webhook.py

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

# Добавляем в datetime fields
_DATETIME_FIELDS = {"created_at", "updated_at", "calculated_at", "ai_generated_at"}
```

**Чеклист Этап 10:**
- [ ] Добавить новые поля в _USER_FIELDS_DEFAULTS
- [ ] Добавить ai_generated_at в _DATETIME_FIELDS
- [ ] Протестировать отправку в n8n

---

## 📊 Тестирование

### Чеклист финального тестирования:

**База данных:**
- [ ] Таблицы созданы (users, body_type_images, bot_settings)
- [ ] Миграция работает на существующей БД
- [ ] Все новые поля присутствуют

**Опрос (FSM):**
- [ ] Пол → Возраст → Рост → Вес → Желаемый вес
- [ ] Показ 4 фото текущей фигуры
- [ ] Показ 4 фото желаемой фигуры
- [ ] Выбор часового пояса
- [ ] Активность → Цель

**Проверка подписки:**
- [ ] Блокирует, если не подписан
- [ ] Пропускает, если подписан
- [ ] Кнопка "Проверить подписку" работает

**AI-рекомендации:**
- [ ] Генерируются корректно
- [ ] Сохраняются в БД
- [ ] Показываются в правильном формате

**Оффер:**
- [ ] Текст редактируется в админке
- [ ] Кнопка "Написать тренеру" работает

**Drip-рассылка:**
- [ ] Включение/отключение через админку
- [ ] При выключении не отправляется

**Админ-панель:**
- [ ] Загрузка изображений работает
- [ ] Редактирование настроек работает
- [ ] Новые колонки отображаются
- [ ] Просмотр AI-рекомендаций работает

**Webhook:**
- [ ] Все новые поля отправляются в n8n
- [ ] Google Sheets обновляется

---

## ⏱️ Итоговый timeline

| Этап | Описание | Время |
|------|----------|-------|
| 1 | База данных | 1 день |
| 2 | FSM States | 30 мин |
| 3 | Константы и тексты | 30 мин |
| 4 | OpenRouter AI | 1-2 часа |
| 5 | Handlers - новые вопросы | 2-3 часа |
| 6 | Проверка подписки | 1 час |
| 7 | Расчет + AI + Оффер | 2 часа |
| 8 | Управление Drip | 30 мин |
| 9 | Админ-панель | 3-4 часа |
| 10 | Webhook | 30 мин |
| **Итого** | | **~3-4 дня** |

---

## 🚀 Порядок выполнения

### День 1:
- ✅ Этап 1: База данных (утро)
- ✅ Этап 2-3: FSM + константы (обед)
- ✅ Этап 4: OpenRouter AI (вечер)

### День 2:
- ✅ Этап 5: Handlers новых вопросов (утро)
- ✅ Этап 6: Проверка подписки (обед)
- ✅ Этап 7: Расчет + AI + Оффер (вечер)

### День 3:
- ✅ Этап 8-10: Drip + Webhook (утро)
- ✅ Этап 9: Админ-панель (день)
- ✅ Тестирование (вечер)

### День 4 (резерв):
- Доработки и фиксы
- Deploy на production

---

## 📝 После завершения

1. **Загрузить изображения в админке:**
   - 4 мужских текущих
   - 4 мужских целевых
   - 4 женских текущих
   - 4 женских целевых

2. **Настроить в админке:**
   - Текст оффера
   - Включить/выключить drip

3. **Проверить .env:**
   ```env
   OPENROUTER_API_KEY=sk-or-v1-xxx
   REQUIRED_CHANNEL_ID=@your_channel
   REQUIRED_CHANNEL_URL=https://t.me/your_channel
   ```

4. **Протестировать с реальными пользователями**

---

## Готов начать?

Скажи "да", и я начну с Этапа 1 (База данных)! 🚀

Или если хочешь изменить порядок/план - скажи как удобнее.

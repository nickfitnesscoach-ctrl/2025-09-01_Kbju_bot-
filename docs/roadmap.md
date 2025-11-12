# Roadmap: Превращение КБЖУ калькулятора в полноценный AI-тест

## Обзор
Трансформация простого калькулятора КБЖУ в интеллектуальный опросник с AI-рекомендациями (через OpenRouter GPT-4 mini), визуальным выбором типа фигуры и персонализированными советами.

---

## Новая цепочка вопросов

### Полная последовательность
1. **Пол** → `gender` (male/female)
2. **Возраст** → `age` (integer)
3. **Рост** → `height` (integer, см)
4. **Вес текущий** → `weight` (float, кг)
5. **Желаемый вес** → `target_weight` (float, кг) 🆕
6. **Текущая фигура** → `current_body_type` (string: "1", "2", "3", "4") 🆕
   - Показываем 4 фото в медиа-группе
   - Кнопки в ряд: [1] [2] [3] [4]
7. **Желаемая фигура** → `target_body_type` (string: "1", "2", "3", "4") 🆕
   - Показываем 4 фото в медиа-группе (разные от текущей)
   - Кнопки в ряд: [1] [2] [3] [4]
8. **Часовой пояс** → `timezone` (string) 🆕
   - Список: МСК, СПб, Казань, Уфа, Тюмень, Екатеринбург, Новосибирск, Красноярск, Иркутск, Владивосток + Европа
   - Кнопки в несколько рядов
9. **Активность** → `activity` (low/moderate/high/very_high)
10. **Цель** → `goal` (weight_loss/maintenance/weight_gain)
11. **Проверка подписки на канал** 🆕
    - Если не подписан → показываем кнопку "Подписаться" + "Проверить подписку"
    - Если подписан → переходим дальше
12. **Расчет КБЖУ** (существующая логика)
13. **AI-рекомендации** (OpenRouter GPT-4 mini) 🆕
14. **Оффер "Написать тренеру"** 🆕
15. **Drip-рассылка** (можно включить/отключить в админке) 🆕

---

## Архитектура изменений

### 1. Модель данных (database/models.py)

**Новые поля в таблице `User`:**

```python
# Новые поля для расширенного опроса
target_weight: Mapped[float] = mapped_column(Float, nullable=True)  # желаемый вес
current_body_type: Mapped[str] = mapped_column(String(10), nullable=True)  # "1", "2", "3", "4"
target_body_type: Mapped[str] = mapped_column(String(10), nullable=True)  # "1", "2", "3", "4"
timezone: Mapped[str] = mapped_column(String(50), nullable=True)  # "msk", "spb", "kazan", etc.

# AI-рекомендации
ai_recommendations: Mapped[str] = mapped_column(String(4000), nullable=True)  # текст рекомендаций
ai_generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # когда сгенерировано

# Telegram file_id для изображений (хранятся в БД для быстрой загрузки)
# Примечание: file_id изображений хранятся отдельно в таблице body_type_images
```

**Новая таблица для хранения изображений фигур:**

```python
class BodyTypeImage(Base):
    """Хранение Telegram file_id для изображений типов фигур"""
    __tablename__ = 'body_type_images'

    id: Mapped[int] = mapped_column(primary_key=True)
    gender: Mapped[str] = mapped_column(String(10))  # "male" or "female"
    category: Mapped[str] = mapped_column(String(20))  # "current" or "target"
    type_number: Mapped[str] = mapped_column(String(5))  # "1", "2", "3", "4"
    file_id: Mapped[str] = mapped_column(String(200))  # Telegram file_id
    caption: Mapped[str] = mapped_column(String(200), nullable=True)  # подпись под фото
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Уникальный индекс: один file_id на комбинацию gender + category + type_number
    __table_args__ = (
        Index('idx_body_image_unique', 'gender', 'category', 'type_number', unique=True),
    )
```

**Новая таблица для кастомизации текстов:**

```python
class BotSettings(Base):
    """Настройки бота (тексты, флаги)"""
    __tablename__ = 'bot_settings'

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)  # "offer_text", "drip_enabled"
    value: Mapped[str] = mapped_column(String(2000))  # значение настройки
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

### 2. Состояния бота (FSM)

**Обновленная структура состояний:**

```python
class KbjuForm(StatesGroup):
    # Существующие состояния
    gender = State()
    age = State()
    weight = State()
    height = State()

    # Новые состояния (до activity)
    target_weight = State()          # Желаемый вес
    current_body_type = State()      # Выбор текущей фигуры (4 фото)
    target_body_type = State()       # Выбор желаемой фигуры (4 фото)
    timezone = State()               # Выбор часового пояса

    # Продолжение существующих
    activity = State()
    goal = State()

    # Проверка подписки перед AI
    checking_subscription = State()  # Ожидание подписки на канал
```

---

### 3. Хранение изображений фигур

**Подход: Telegram file_id**

1. **Загрузка через админ-панель:**
   - Админ загружает 16 изображений (8 мужских, 8 женских)
   - Бот получает `file_id` от Telegram
   - Сохраняем `file_id` в таблицу `body_type_images`

2. **Структура:**
   - **Мужские текущие:** 4 фото → file_id сохраняются как `gender=male, category=current, type_number=1/2/3/4`
   - **Мужские целевые:** 4 фото → `gender=male, category=target, type_number=1/2/3/4`
   - **Женские текущие:** 4 фото → `gender=female, category=current, type_number=1/2/3/4`
   - **Женские целевые:** 4 фото → `gender=female, category=target, type_number=1/2/3/4`

3. **Отображение пользователю:**
   ```python
   # Получаем file_id из БД
   images = await get_body_type_images(gender="male", category="current")

   # Отправляем медиа-группу
   media_group = [
       InputMediaPhoto(media=img.file_id, caption=img.caption or f"Тип {img.type_number}")
       for img in images
   ]
   await message.answer_media_group(media_group)

   # Кнопки в ряд
   keyboard = InlineKeyboardMarkup(inline_keyboard=[
       [
           InlineKeyboardButton(text="1", callback_data="body_current_1"),
           InlineKeyboardButton(text="2", callback_data="body_current_2"),
           InlineKeyboardButton(text="3", callback_data="body_current_3"),
           InlineKeyboardButton(text="4", callback_data="body_current_4"),
       ]
   ])
   ```

---

### 4. Часовые пояса России + Европа

**Полный список:**

```python
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
```

**Кнопки в несколько рядов (по 2-3 в ряд):**

```python
keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🏛 Москва", callback_data="tz_msk"),
        InlineKeyboardButton(text="🏰 СПб", callback_data="tz_spb"),
    ],
    [
        InlineKeyboardButton(text="🕌 Казань", callback_data="tz_kazan"),
        InlineKeyboardButton(text="🏔 Уфа", callback_data="tz_ufa"),
    ],
    # ... и т.д.
])
```

---

### 5. AI-рекомендации через OpenRouter (GPT-4 mini)

**API: OpenRouter**
- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Модель: `openai/gpt-4o-mini`

**Конфигурация (config.py):**

```python
# OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = 'openai/gpt-4o-mini'
OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
```

**Функция генерации (app/services/ai_recommendations.py):**

```python
import aiohttp
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_ENDPOINT

async def generate_ai_recommendations(user_data: dict) -> str:
    """
    Генерирует персонализированные рекомендации через OpenRouter GPT-4 mini

    Формат как на скрине:
    📊 Анализ текущего состояния
    🎯 Безопасные цели
    🎨 Ожидаемые изменения
    🏋️ Целевые тренировки
    🍽 Рамки по питанию
    """

    prompt = f"""
Ты профессиональный фитнес-тренер и нутрициолог. Проанализируй данные клиента и дай персонализированный ответ.

📋 Данные клиента:
• Пол: {user_data['gender']}
• Возраст: {user_data['age']} лет
• Рост: {user_data['height']} см
• Текущий вес: {user_data['weight']} кг
• Желаемый вес: {user_data['target_weight']} кг
• Разница: {user_data['weight'] - user_data['target_weight']:.1f} кг
• Уровень активности: {user_data['activity']}
• Цель: {user_data['goal']}
• Текущий тип фигуры: {user_data['current_body_type']}
• Желаемый тип фигуры: {user_data['target_body_type']}
• Часовой пояс: {user_data['timezone']}

📊 Рассчитанные КБЖУ:
• Калории: {user_data['calories']} ккал/день
• Белки: {user_data['proteins']} г
• Жиры: {user_data['fats']} г
• Углеводы: {user_data['carbs']} г

---

Дай ответ СТРОГО в следующем формате (используй эмодзи и структуру):

📊 **Анализ текущего состояния**
[2-3 предложения: BMI, оценка веса, процент жира, тип фигуры]

🎯 **Безопасные цели**
[Реалистичный срок достижения цели, темп снижения/набора веса в неделю]

🎨 **Ожидаемые изменения**
• [изменение 1]
• [изменение 2]
• [изменение 3]

🏋️ **Целевые тренировки**
• [рекомендация по частоте тренировок]
• [тип нагрузок: силовые/кардио/интервалы]

🍽 **Рамки по питанию**
[Краткие принципы: дефицит/профицит, распределение БЖУ, примеры продуктов]

---

⚠️ Важно:
- Будь кратким (до 800 символов)
- Используй только указанные секции
- Не добавляй дополнительные разделы
- Говори по-русски, на "ты"
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Ты профессиональный фитнес-тренер и нутрициолог."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1200,
        "temperature": 0.7,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(OPENROUTER_ENDPOINT, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"OpenRouter API error: {resp.status}")

            data = await resp.json()
            return data['choices'][0]['message']['content']
```

---

### 6. Проверка подписки на канал

**Перед AI-рекомендациями проверяем подписку:**

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import REQUIRED_CHANNEL_ID  # например: "@your_channel"

async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


@router.callback_query(lambda c: c.data.startswith("tz_"))
async def process_timezone(callback: types.CallbackQuery, state: FSMContext):
    """После выбора часового пояса → activity"""
    timezone = callback.data.split("_")[1]
    await state.update_data(timezone=timezone)

    # Переходим к вопросу об активности
    # ... (существующая логика)


@router.callback_query(lambda c: c.data == "goal_...")
async def process_goal_and_check_subscription(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """После цели → проверка подписки"""
    goal = callback.data.split("_")[1]
    await state.update_data(goal=goal)

    # Проверяем подписку
    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{REQUIRED_CHANNEL_ID.replace('@', '')}")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")],
        ])
        await callback.message.answer(
            "Для получения AI-рекомендаций подпишитесь на наш канал:",
            reply_markup=keyboard
        )
        await state.set_state(KbjuForm.checking_subscription)
    else:
        # Сразу переходим к расчету и AI
        await calculate_and_generate_ai(callback, state, bot)


@router.callback_query(lambda c: c.data == "check_subscription")
async def recheck_subscription(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Повторная проверка подписки"""
    is_subscribed = await check_subscription(bot, callback.from_user.id)

    if is_subscribed:
        await callback.answer("✅ Подписка подтверждена!")
        await calculate_and_generate_ai(callback, state, bot)
    else:
        await callback.answer("❌ Вы еще не подписались на канал", show_alert=True)
```

---

### 7. Оффер "Написать тренеру"

**Текст оффера (редактируемый в админке):**

```python
# В БД (bot_settings):
key = "offer_text"
value = """
💪 Хочешь получить план питания и тренировок и более предметные рекомендации?

📲 Напиши тренеру!
"""

# Функция показа оффера:
async def show_trainer_offer(message: types.Message):
    """Показывает оффер с кнопкой связи с тренером"""

    # Получаем текст из БД
    offer_text = await get_setting("offer_text") or "Напишите тренеру для консультации"

    # Получаем Telegram ID админа/тренера
    trainer_username = ADMIN_USERNAME  # из config.py

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✉️ Написать тренеру",
            url=f"https://t.me/{trainer_username}"
        )],
    ])

    await message.answer(offer_text, reply_markup=keyboard)
```

**Конфигурация (config.py):**

```python
# Telegram ID/username админа (тренера)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'your_username')  # без @
ADMIN_TG_ID = int(os.getenv('ADMIN_TG_ID', '123456789'))

# ID канала для обязательной подписки
REQUIRED_CHANNEL_ID = os.getenv('REQUIRED_CHANNEL_ID', '@your_channel')
```

---

### 8. Drip-рассылка (включение/отключение)

**В админ-панели добавляем переключатель:**

```python
# В БД (bot_settings):
key = "drip_enabled"
value = "true"  # или "false"

# В коде:
async def is_drip_enabled() -> bool:
    """Проверяет, включена ли drip-рассылка"""
    setting = await get_setting("drip_enabled")
    return setting == "true"

# При отправке follow-up сообщений:
if not await is_drip_enabled():
    logger.info("Drip campaign is disabled, skipping follow-up for user %s", user_id)
    return
```

**В админ-панели:**
- Переключатель "Drip-рассылка: ВКЛ/ВЫКЛ"
- Кнопка "Сохранить настройки"

---

### 9. Админ-панель: новые функции

**9.1. Загрузка изображений фигур**

Новая страница: `/admin/body_images`

```python
@admin_router.get("/body_images")
async def body_images_page():
    """Страница управления изображениями фигур"""
    images = await get_all_body_type_images()

    return render_template("body_images.html", images=images)


@admin_router.post("/upload_body_image")
async def upload_body_image(
    gender: str,
    category: str,
    type_number: str,
    caption: str,
    file: UploadFile
):
    """Загрузка изображения в Telegram и сохранение file_id"""

    # 1. Отправляем фото боту для получения file_id
    from aiogram import Bot
    from config import TOKEN

    bot = Bot(token=TOKEN)
    message = await bot.send_photo(
        chat_id=ADMIN_TG_ID,
        photo=file.file,
        caption=f"Загружено: {gender} - {category} - тип {type_number}"
    )
    file_id = message.photo[-1].file_id

    # 2. Сохраняем в БД
    await save_body_type_image(
        gender=gender,
        category=category,
        type_number=type_number,
        file_id=file_id,
        caption=caption
    )

    return {"success": True, "file_id": file_id}
```

**HTML форма (body_images.html):**

```html
<h2>Управление изображениями фигур</h2>

<form method="POST" action="/upload_body_image" enctype="multipart/form-data">
    <label>Пол:</label>
    <select name="gender">
        <option value="male">Мужской</option>
        <option value="female">Женский</option>
    </select>

    <label>Категория:</label>
    <select name="category">
        <option value="current">Текущая фигура</option>
        <option value="target">Желаемая фигура</option>
    </select>

    <label>Тип (номер):</label>
    <select name="type_number">
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
        <option value="4">4</option>
    </select>

    <label>Подпись (опционально):</label>
    <input type="text" name="caption" placeholder="Например: Стройная фигура">

    <label>Файл:</label>
    <input type="file" name="file" accept="image/*" required>

    <button type="submit">Загрузить</button>
</form>

<hr>

<h3>Загруженные изображения</h3>
<table>
    <thead>
        <tr>
            <th>Пол</th>
            <th>Категория</th>
            <th>Тип</th>
            <th>Подпись</th>
            <th>Превью</th>
            <th>Действия</th>
        </tr>
    </thead>
    <tbody>
        {% for img in images %}
        <tr>
            <td>{{ img.gender }}</td>
            <td>{{ img.category }}</td>
            <td>{{ img.type_number }}</td>
            <td>{{ img.caption }}</td>
            <td><img src="https://api.telegram.org/file/bot{TOKEN}/{{ img.file_id }}" width="100"></td>
            <td><button onclick="deleteImage({{ img.id }})">Удалить</button></td>
        </tr>
        {% endfor %}
    </tbody>
</table>
```

**9.2. Редактирование текстов (оффер, drip-флаг)**

Новая страница: `/admin/settings`

```python
@admin_router.get("/settings")
async def settings_page():
    """Страница настроек бота"""
    offer_text = await get_setting("offer_text")
    drip_enabled = await get_setting("drip_enabled") == "true"

    return render_template("settings.html", offer_text=offer_text, drip_enabled=drip_enabled)


@admin_router.post("/save_settings")
async def save_settings(offer_text: str, drip_enabled: bool):
    """Сохранение настроек"""
    await set_setting("offer_text", offer_text)
    await set_setting("drip_enabled", "true" if drip_enabled else "false")

    return {"success": True}
```

**HTML форма (settings.html):**

```html
<h2>Настройки бота</h2>

<form method="POST" action="/save_settings">
    <label>Текст оффера (после AI-рекомендаций):</label>
    <textarea name="offer_text" rows="5">{{ offer_text }}</textarea>

    <label>
        <input type="checkbox" name="drip_enabled" {% if drip_enabled %}checked{% endif %}>
        Включить Drip-рассылку
    </label>

    <button type="submit">Сохранить</button>
</form>
```

**9.3. Отображение новых полей в списке лидов**

Обновляем страницу `/admin/leads`:

```python
# Добавляем новые колонки:
columns_to_show = [
    'id', 'tg_id', 'username', 'first_name',
    'gender', 'age', 'weight', 'height',
    'target_weight',  # 🆕
    'current_body_type',  # 🆕
    'target_body_type',  # 🆕
    'timezone',  # 🆕
    'activity', 'goal',
    'calories', 'proteins', 'fats', 'carbs',
    'funnel_status',
    'created_at', 'calculated_at',
    'ai_generated_at',  # 🆕
]
```

**Просмотр AI-рекомендаций:**

```python
@admin_router.get("/lead/{lead_id}/ai_recommendations")
async def view_ai_recommendations(lead_id: int):
    """Просмотр AI-рекомендаций для конкретного лида"""
    user = await get_user_by_id(lead_id)

    if not user or not user.ai_recommendations:
        return {"error": "Рекомендации не найдены"}

    return render_template("ai_recommendations.html",
                         user=user,
                         recommendations=user.ai_recommendations)
```

---

### 10. Webhook (app/webhook.py)

**Обновляем `_USER_FIELDS_DEFAULTS` для новых полей:**

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

# Добавляем в список datetime полей
_DATETIME_FIELDS = {"created_at", "updated_at", "calculated_at", "ai_generated_at"}
```

**Теперь все новые данные будут отправляться в Google Sheets через n8n.**

---

## План реализации (пошаговый)

### Этап 1: Подготовка базы данных
- [ ] Добавить новые поля в модель `User`
- [ ] Создать таблицу `BodyTypeImage`
- [ ] Создать таблицу `BotSettings`
- [ ] Написать миграции `_ensure_extended_survey_columns()`
- [ ] Протестировать создание таблиц в SQLite

### Этап 2: Админ-панель - управление изображениями
- [ ] Создать страницу `/admin/body_images`
- [ ] Реализовать загрузку изображений через форму
- [ ] Получать `file_id` от Telegram при загрузке
- [ ] Сохранять в таблицу `body_type_images`
- [ ] Показывать список загруженных изображений с превью

### Этап 3: Админ-панель - настройки бота
- [ ] Создать страницу `/admin/settings`
- [ ] Добавить редактирование текста оффера
- [ ] Добавить переключатель drip-рассылки (вкл/выкл)
- [ ] Реализовать сохранение настроек в `bot_settings`

### Этап 4: FSM - новые состояния и handlers
- [ ] Добавить состояния: `target_weight`, `current_body_type`, `target_body_type`, `timezone`, `checking_subscription`
- [ ] Написать handler для вопроса "желаемый вес"
- [ ] Написать handler для показа 4 фото "текущая фигура" + кнопки [1][2][3][4]
- [ ] Написать handler для показа 4 фото "желаемая фигура" + кнопки [1][2][3][4]
- [ ] Написать handler для выбора часового пояса (список всех городов)
- [ ] Перенести вопросы `activity` и `goal` после новых вопросов

### Этап 5: Проверка подписки на канал
- [ ] Добавить `REQUIRED_CHANNEL_ID` в config.py
- [ ] Написать функцию `check_subscription()`
- [ ] Добавить проверку после вопроса "Цель"
- [ ] Показывать кнопки "Подписаться" + "Проверить подписку"
- [ ] Блокировать переход к AI до подтверждения подписки

### Этап 6: AI-интеграция (OpenRouter GPT-4 mini)
- [ ] Добавить `OPENROUTER_API_KEY` в config.py и .env
- [ ] Создать файл `app/services/ai_recommendations.py`
- [ ] Написать функцию `generate_ai_recommendations()`
- [ ] Разработать промпт (формат как на скрине)
- [ ] Протестировать генерацию рекомендаций
- [ ] Сохранять результат в `user.ai_recommendations` и `ai_generated_at`

### Этап 7: Оффер "Написать тренеру"
- [ ] Добавить `ADMIN_USERNAME` и `ADMIN_TG_ID` в config.py
- [ ] Создать функцию `show_trainer_offer()`
- [ ] Получать текст оффера из `bot_settings` (редактируемый)
- [ ] Добавить кнопку с URL на личку тренера
- [ ] Вызывать после показа AI-рекомендаций

### Этап 8: Drip-рассылка (управление)
- [ ] Добавить проверку `is_drip_enabled()` в логику follow-up
- [ ] При выключенном флаге → пропускать отправку drip-сообщений
- [ ] Тестировать переключение через админку

### Этап 9: Обновление webhook и админки
- [ ] Обновить `_USER_FIELDS_DEFAULTS` в webhook.py
- [ ] Протестировать отправку расширенных данных в n8n → Google Sheets
- [ ] Добавить новые колонки в админ-панель `/admin/leads`
- [ ] Создать страницу просмотра AI-рекомендаций `/admin/lead/{id}/ai_recommendations`

### Этап 10: Тестирование и deploy
- [ ] End-to-end тест полной цепочки (от /start до оффера)
- [ ] Проверка сохранения всех данных в БД
- [ ] Проверка отображения в админ-панели
- [ ] Проверка отправки в Google Sheets
- [ ] Проверка генерации AI-рекомендаций
- [ ] Deploy на production
- [ ] Загрузка всех 16 изображений через админку

---

## Технические детали

### Зависимости (requirements.txt)

Добавить:
```
aiohttp>=3.9.0  # для запросов к OpenRouter
pillow>=10.0.0  # для обработки изображений (если нужно)
```

### Конфигурация (config.py)

Добавить:
```python
# OpenRouter API
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = 'openai/gpt-4o-mini'
OPENROUTER_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'

# Telegram admin
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'your_username')  # без @
ADMIN_TG_ID = int(os.getenv('ADMIN_TG_ID', '123456789'))

# Обязательная подписка
REQUIRED_CHANNEL_ID = os.getenv('REQUIRED_CHANNEL_ID', '@your_channel')
```

### .env

Добавить:
```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
ADMIN_USERNAME=your_telegram_username
ADMIN_TG_ID=123456789
REQUIRED_CHANNEL_ID=@your_channel
```

---

## Итоговый флоу пользователя

```
START
  ↓
1. Пол → male/female
  ↓
2. Возраст → 25
  ↓
3. Рост → 180 см
  ↓
4. Вес текущий → 85 кг
  ↓
5. Желаемый вес → 75 кг 🆕
  ↓
6. Текущая фигура → [медиа-группа 4 фото] → кнопки [1][2][3][4] → выбор "2" 🆕
  ↓
7. Желаемая фигура → [медиа-группа 4 фото] → кнопки [1][2][3][4] → выбор "1" 🆕
  ↓
8. Часовой пояс → [список городов] → выбор "Москва" 🆕
  ↓
9. Активность → moderate
  ↓
10. Цель → weight_loss
  ↓
11. Проверка подписки на канал 🆕
    ├─ Не подписан → "Подпишитесь" + "Проверить подписку"
    └─ Подписан → продолжаем
  ↓
12. Расчет КБЖУ → 2200 ккал, Б: 165г, Ж: 73г, У: 220г
  ↓
13. AI-рекомендации → "📊 Анализ текущего состояния..." 🆕
  ↓
14. Оффер → "Напиши тренеру!" + кнопка [✉️ Написать тренеру] 🆕
  ↓
15. Drip-рассылка (если включена в админке) 🆕
  ↓
END
```

---

## Схема базы данных (обновленная)

```sql
-- Таблица users (обновленная)
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    tg_id BIGINT UNIQUE,
    username VARCHAR(50),
    first_name VARCHAR(100),
    gender VARCHAR(10),
    age INTEGER,
    weight FLOAT,
    height INTEGER,
    target_weight FLOAT,  -- 🆕
    current_body_type VARCHAR(10),  -- 🆕
    target_body_type VARCHAR(10),  -- 🆕
    timezone VARCHAR(50),  -- 🆕
    activity VARCHAR(20),
    goal VARCHAR(20),
    calories INTEGER,
    proteins INTEGER,
    fats INTEGER,
    carbs INTEGER,
    ai_recommendations TEXT,  -- 🆕
    ai_generated_at DATETIME,  -- 🆕
    funnel_status VARCHAR(20),
    hot_lead_notified_at DATETIME,
    last_activity_at DATETIME,
    drip_stage INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME,
    calculated_at DATETIME
);

-- Новая таблица для изображений 🆕
CREATE TABLE body_type_images (
    id INTEGER PRIMARY KEY,
    gender VARCHAR(10),  -- 'male' or 'female'
    category VARCHAR(20),  -- 'current' or 'target'
    type_number VARCHAR(5),  -- '1', '2', '3', '4'
    file_id VARCHAR(200),  -- Telegram file_id
    caption VARCHAR(200),
    uploaded_at DATETIME,
    UNIQUE(gender, category, type_number)
);

-- Новая таблица для настроек 🆕
CREATE TABLE bot_settings (
    id INTEGER PRIMARY KEY,
    key VARCHAR(100) UNIQUE,  -- 'offer_text', 'drip_enabled'
    value TEXT,
    updated_at DATETIME
);
```

---

## Безопасность

- ✅ OpenRouter API key хранится в `.env`
- ✅ Валидация пользовательского ввода (вес, возраст)
- ✅ Rate limiting для AI запросов (защита от злоупотреблений)
- ✅ Проверка подписки на канал перед доступом к AI
- ✅ file_id изображений хранятся в БД (не локальные пути)

---

## Скрин пример AI-рекомендаций

Формат из скрина:

```
📊 Анализ текущего состояния
Ты 23 года, 170 см, 71.0 кг — BMI 24.6 (практически на грани нормального/избыточного). Судя по весу и оценке жира (~25% по фото, это приблизительно), у тебя тип фигуры: стройная с небольшой полнотой в талии/бедрах. Процент жира — ориентир, не точное измерение.

🎯 Безопасные цели
Ты хочешь 62.5 кг (минус 8.5 кг). Реалистично и безопасно: примерно 8.5 кг за 11–17 недель при дефиците ~0.5–0.75 кг/нед.

🎨 Ожидаемые изменения
• уменьшение объемов в талии и бедрах
• более подтянутая линия корпуса, слегка проглядывающая мышечная масса
• лучшее самочувствие и энергия

🏋️ Целевые тренировки
• постепенно увеличить до 3–4 тренировок в неделю: 2–3 силовые + 1–2 кардио/интервала
• фокус на базовых упражнениях (приседы, тяги, жимы, планка)

🍽 Рамки по питанию
Точные цифры очень индивидуальны, тренер должен погрузиться в твою ситуацию.
```

---

**Статус:** Roadmap готов. Ожидание твоего одобрения для начала реализации.

# Стратегия интеграции: КБЖУ по фото + Панель тренера

## Текущая ситуация

### Проект 1: КБЖУ калькулятор (лид-магнит) - **ТЕКУЩИЙ ПРОЕКТ**
- ✅ Telegram бот с опросом (пол, возраст, вес, рост, активность, цель)
- ✅ Расчет КБЖУ по формуле Harris-Benedict
- ✅ Интеграция с n8n → Google Sheets
- ✅ Drip-рассылка для лидов
- ✅ Проверка подписки на канал
- ✅ Admin панель Flask (просмотр лидов, статистика)
- ✅ База данных SQLite с таблицей `users`

### Проект 2: КБЖУ по фото с подпиской (упомянутый)
- Backend для расчета КБЖУ по фотографии
- Система подписки/платежей
- Работа с клиентами тренера

---

## 🎯 Целевая архитектура: Единый бот с 3 режимами

```
┌─────────────────────────────────────────────────────────┐
│              ЕДИНЫЙ TELEGRAM БОТ                        │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐  ┌──────────────┐  ┌─────────────────┐
│  РЕЖИМ 1:     │  │  РЕЖИМ 2:    │  │  РЕЖИМ 3:       │
│  Лид-магнит   │  │  Платные     │  │  Панель тренера │
│  (бесплатный) │  │  клиенты     │  │  (Mini App)     │
└───────────────┘  └──────────────┘  └─────────────────┘
       │                  │                    │
       │                  │                    │
       ▼                  ▼                    ▼
┌─────────────┐  ┌────────────────┐  ┌──────────────────┐
│ • Опрос     │  │ • Загрузка фото│  │ • Список заявок  │
│ • КБЖУ      │  │ • AI анализ    │  │ • Карточки лидов │
│ • AI совет  │  │ • Подписка     │  │ • Связь с лидами │
│ • Оффер     │  │ • Персональный │  │ • Конвертация    │
│ • Drip      │  │   план питания │  │ • Реф. ссылка    │
└─────────────┘  └────────────────┘  └──────────────────┘
```

---

## 🏗️ Варианты интеграции

### Вариант 1: ЕДИНАЯ КОДОВАЯ БАЗА (Рекомендуется ⭐)

**Концепция:** Объединить оба проекта в один репозиторий с модульной архитектурой.

```
fitness_bot/                          # Единый проект
├── app/
│   ├── core/                         # Общие компоненты
│   │   ├── database/
│   │   │   ├── models.py            # Общие модели (User, Subscription, etc.)
│   │   │   └── requests.py
│   │   ├── auth.py                  # Аутентификация, роли
│   │   └── payments.py              # Платежная система
│   │
│   ├── lead_magnet/                 # 🆕 Режим 1: Лид-магнит
│   │   ├── handlers/
│   │   │   ├── kbju_survey.py      # Опрос для бесплатного КБЖУ
│   │   │   ├── ai_recommendations.py
│   │   │   └── offer.py
│   │   ├── calculator.py           # Расчет КBЖУ
│   │   └── drip_followups.py       # Догоняющие кейсы
│   │
│   ├── photo_analysis/              # 🆕 Режим 2: КБЖУ по фото
│   │   ├── handlers/
│   │   │   ├── photo_upload.py
│   │   │   ├── ai_analysis.py
│   │   │   └── subscription.py
│   │   ├── vision_api.py           # Интеграция с OpenAI Vision / Gemini
│   │   └── meal_planner.py         # Генерация планов питания
│   │
│   ├── trainer_panel/               # 🆕 Режим 3: Панель тренера
│   │   ├── mini_app/
│   │   │   ├── routes.py           # API для Mini App
│   │   │   ├── auth.py
│   │   │   └── static/             # HTML/CSS/JS
│   │   └── handlers/
│   │       └── panel_access.py     # Команда /panel
│   │
│   ├── admin/                       # Админ-панель (Flask)
│   │   ├── admin_panel.py
│   │   ├── routes/
│   │   │   ├── leads.py
│   │   │   ├── clients.py
│   │   │   ├── subscriptions.py
│   │   │   └── settings.py
│   │   └── templates/
│   │
│   └── shared/                      # Общие утилиты
│       ├── keyboards.py
│       ├── texts.py
│       └── webhook.py              # n8n интеграция
│
├── config.py                        # Единая конфигурация
├── run_bot.py                       # Запуск Telegram бота
├── run_admin.py                     # Запуск админ-панели
└── requirements.txt
```

**Преимущества:**
- ✅ Единая база данных для всех пользователей
- ✅ Один бот, одна админ-панель
- ✅ Переиспользование кода (калькулятор, AI, тексты)
- ✅ Легче поддерживать и обновлять
- ✅ Единая система платежей

**Недостатки:**
- ⚠️ Требуется рефакторинг текущего кода
- ⚠️ Больше времени на миграцию (3-5 дней)

---

### Вариант 2: МИКРОСЕРВИСНАЯ АРХИТЕКТУРА

**Концепция:** Два отдельных проекта с общей базой данных и API.

```
┌──────────────────────────┐        ┌──────────────────────────┐
│   Проект 1:              │        │   Проект 2:              │
│   Лид-магнит бот         │◄──────►│   КБЖУ по фото бот       │
│   (текущий)              │  API   │   (новый)                │
└──────────────────────────┘        └──────────────────────────┘
            │                                   │
            │         ┌────────────────┐        │
            └────────►│  Общая БД      │◄───────┘
                      │  PostgreSQL    │
                      └────────────────┘
                              │
                      ┌───────▼────────┐
                      │  Mini App      │
                      │  (отдельно)    │
                      └────────────────┘
```

**Преимущества:**
- ✅ Минимальные изменения в текущем проекте
- ✅ Проекты изолированы друг от друга
- ✅ Можно разрабатывать параллельно

**Недостатки:**
- ❌ Дублирование кода (калькулятор, тексты, логика)
- ❌ Две админ-панели или сложная интеграция
- ❌ Сложнее синхронизировать данные
- ❌ Больше накладных расходов на инфраструктуру

---

### Вариант 3: ПОЭТАПНАЯ ИНТЕГРАЦИЯ (Компромисс)

**Концепция:** Начать с микросервисов, постепенно мигрировать в единую базу.

**Этап 1 (1-2 недели):**
- Сохранить текущий проект как есть (лид-магнит)
- Добавить Mini App в текущий проект
- Создать отдельный бот для КБЖУ по фото

**Этап 2 (2-3 недели):**
- Объединить базы данных
- Создать общую систему аутентификации

**Этап 3 (1-2 недели):**
- Объединить ботов в один с разными точками входа
- Рефакторинг в единую кодовую базу

---

## 🎯 Рекомендация: Вариант 1 (Единая кодовая база)

### Почему?

1. **Пользовательский опыт:**
   - Один бот для всего → проще для пользователей
   - Единая база данных → история пользователя в одном месте
   - Легко переводить лидов в платных клиентов

2. **Разработка:**
   - Переиспользование кода (AI, калькулятор, тексты)
   - Единая админ-панель для всех функций
   - Проще тестировать и деплоить

3. **Бизнес:**
   - Лид-магнит → платная подписка (smooth transition)
   - Панель тренера видит всех: и бесплатных лидов, и платных клиентов
   - Единая аналитика и отчетность

---

## 📋 План миграции (Вариант 1)

### Фаза 1: Подготовка (1 день)

**Задачи:**
- [ ] Backup текущего проекта и базы данных
- [ ] Создать новую ветку `integration/photo-analysis`
- [ ] Изучить код проекта с КБЖУ по фото
- [ ] Определить общие компоненты

**Результат:** Понимание архитектуры обоих проектов

---

### Фаза 2: Реорганизация структуры (2 дня)

**Задачи:**
- [ ] Создать новую структуру папок:
  ```
  app/
  ├── core/           # Общее
  ├── lead_magnet/    # Режим 1
  ├── photo_analysis/ # Режим 2
  ├── trainer_panel/  # Режим 3
  └── admin/
  ```

- [ ] Перенести текущий код в `lead_magnet/`:
  ```
  app/lead_magnet/
  ├── handlers/
  │   ├── kbju_survey.py     ← из app/user/kbju.py
  │   ├── general.py         ← из app/user/general.py
  │   └── lifecycle.py       ← из app/user/lifecycle.py
  ├── calculator.py          ← из app/calculator.py
  ├── drip_followups.py      ← из app/drip_followups.py
  └── ai_recommendations.py  ← НОВОЕ (из roadmap.md)
  ```

- [ ] Создать `app/core/` для общего кода:
  ```
  app/core/
  ├── database/
  │   ├── models.py          ← расширенная версия из app/database/models.py
  │   └── requests.py        ← из app/database/requests.py
  ├── auth.py                ← НОВОЕ (роли: lead, client, trainer)
  ├── texts.py               ← из app/texts.py
  └── keyboards.py           ← из app/keyboards.py
  ```

**Результат:** Модульная структура проекта

---

### Фаза 3: Расширение базы данных (1 день)

**Задачи:**
- [ ] Добавить новые поля в модель `User`:
  ```python
  # Из roadmap.md (новые поля для лид-магнита)
  target_weight: Mapped[float]
  current_body_type: Mapped[str]
  target_body_type: Mapped[str]
  timezone: Mapped[str]
  ai_recommendations: Mapped[str]

  # НОВОЕ: для КБЖУ по фото
  user_type: Mapped[str]  # "lead", "client", "trainer"
  subscription_status: Mapped[str]  # "none", "active", "expired"
  subscription_expires_at: Mapped[datetime]
  photo_analysis_count: Mapped[int]  # сколько раз загружал фото
  last_photo_id: Mapped[str]  # file_id последнего фото
  ```

- [ ] Создать таблицы:
  ```python
  class Subscription(Base):
      """Подписки пользователей"""
      __tablename__ = 'subscriptions'

      id: Mapped[int]
      user_id: Mapped[int]  # FK → users.id
      plan: Mapped[str]  # "monthly", "yearly"
      status: Mapped[str]  # "active", "expired", "cancelled"
      started_at: Mapped[datetime]
      expires_at: Mapped[datetime]
      payment_id: Mapped[str]  # ID транзакции
      amount: Mapped[float]

  class PhotoAnalysis(Base):
      """История анализов фото"""
      __tablename__ = 'photo_analyses'

      id: Mapped[int]
      user_id: Mapped[int]
      photo_file_id: Mapped[str]
      analysis_result: Mapped[str]  # JSON с результатами AI
      body_fat_percentage: Mapped[float]
      muscle_mass: Mapped[float]
      created_at: Mapped[datetime]
  ```

- [ ] Написать миграции для существующих пользователей

**Результат:** Единая БД для всех режимов

---

### Фаза 4: Интеграция режима "КБЖУ по фото" (3 дня)

**Задачи:**
- [ ] Создать `app/photo_analysis/`:
  ```python
  # handlers/photo_upload.py
  @router.message(F.photo, StateFilter(PhotoAnalysisForm.waiting_photo))
  async def process_photo(message: Message, state: FSMContext):
      # 1. Проверить подписку
      if not await check_subscription(user_id):
          await offer_subscription(message)
          return

      # 2. Загрузить фото
      photo = message.photo[-1]

      # 3. Отправить в AI (OpenAI Vision / Gemini)
      analysis = await analyze_body_photo(photo.file_id)

      # 4. Сохранить результат
      await save_photo_analysis(user_id, photo.file_id, analysis)

      # 5. Показать результаты
      await show_analysis_results(message, analysis)
  ```

- [ ] Интегрировать AI Vision API:
  ```python
  # vision_api.py
  async def analyze_body_photo(file_id: str) -> dict:
      """Анализ фото через OpenAI Vision или Gemini Vision"""

      # Скачать фото
      photo_bytes = await bot.download_file(file_id)

      # Отправить в AI
      prompt = """
      Проанализируй фото тела человека и определи:
      1. Процент жира в организме (приблизительно)
      2. Тип фигуры (эктоморф/мезоморф/эндоморф)
      3. Видимость мышечной массы
      4. Рекомендации по питанию и тренировкам
      """

      result = await openai.chat.completions.create(
          model="gpt-4-vision-preview",
          messages=[{
              "role": "user",
              "content": [
                  {"type": "text", "text": prompt},
                  {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_base64}"}}
              ]
          }]
      )

      return parse_ai_response(result)
  ```

- [ ] Система подписки (Telegram Stars или Stripe):
  ```python
  # payments.py
  async def create_subscription_invoice(user_id: int, plan: str):
      """Создать инвойс для подписки"""

      prices = {
          "monthly": 990,  # руб/мес
          "yearly": 9900   # руб/год
      }

      await bot.send_invoice(
          chat_id=user_id,
          title="Подписка КБЖУ по фото",
          description=f"Безлимитные анализы фото на {plan}",
          payload=f"subscription_{plan}_{user_id}",
          provider_token=PAYMENT_TOKEN,
          currency="RUB",
          prices=[{"label": "Подписка", "amount": prices[plan] * 100}]
      )
  ```

**Результат:** Работающий режим КБЖУ по фото с подпиской

---

### Фаза 5: Добавление Mini App (3 дня)

**Задачи:**
- [ ] Создать `app/trainer_panel/` (из `mini-app-architecture.md`)
- [ ] Реализовать API endpoints для Mini App
- [ ] Создать HTML/CSS/JS для Mini App
- [ ] Интегрировать с текущей БД
- [ ] Команда `/panel` для открытия Mini App

**Результат:** Панель тренера для управления лидами и клиентами

---

### Фаза 6: Единая точка входа (1 день)

**Задачи:**
- [ ] Создать роутер для определения режима пользователя:
  ```python
  # app/core/router.py
  async def route_user(message: Message):
      user = await get_user(message.from_user.id)

      # Тренер → панель тренера
      if user.user_type == "trainer":
          await show_trainer_menu(message)
          return

      # Клиент с подпиской → КБЖУ по фото
      elif user.subscription_status == "active":
          await show_photo_analysis_menu(message)
          return

      # Новый пользователь или лид → лид-магнит
      else:
          await start_lead_magnet_survey(message)
  ```

- [ ] Обновить `/start` команду для маршрутизации
- [ ] Создать меню с кнопками выбора режима

**Результат:** Один бот с умной маршрутизацией

---

### Фаза 7: Обновление админ-панели (2 дня)

**Задачи:**
- [ ] Добавить вкладки в админку:
  ```
  Админ-панель:
  ├── Лиды (бесплатные)
  ├── Клиенты (платные подписки)
  ├── Подписки (управление)
  ├── Анализы фото (история)
  ├── Настройки
  └── Статистика
  ```

- [ ] Отображение новых полей в списке пользователей
- [ ] Фильтры: "Лиды", "Клиенты", "Тренеры"
- [ ] Управление подписками (продлить, отменить)

**Результат:** Единая админ-панель для всех режимов

---

### Фаза 8: Тестирование и запуск (2 дня)

**Задачи:**
- [ ] End-to-end тестирование всех режимов
- [ ] Тест миграции данных
- [ ] Тест платежей
- [ ] Тест Mini App
- [ ] Deploy на production
- [ ] Мониторинг первых пользователей

**Результат:** Единый бот в production

---

## 📊 Итоговая архитектура базы данных

```sql
-- Пользователи (расширенная таблица)
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    tg_id BIGINT UNIQUE,
    username VARCHAR(50),
    first_name VARCHAR(100),

    -- Роль и статус
    user_type VARCHAR(20) DEFAULT 'lead',  -- 'lead', 'client', 'trainer'
    subscription_status VARCHAR(20) DEFAULT 'none',  -- 'none', 'active', 'expired'
    subscription_expires_at DATETIME,

    -- Базовые данные (для лид-магнита и фото)
    gender VARCHAR(10),
    age INTEGER,
    weight FLOAT,
    height INTEGER,
    target_weight FLOAT,

    -- Лид-магнит: выбор фигуры и часовой пояс
    current_body_type VARCHAR(10),
    target_body_type VARCHAR(10),
    timezone VARCHAR(50),

    -- КБЖУ
    activity VARCHAR(20),
    goal VARCHAR(20),
    calories INTEGER,
    proteins INTEGER,
    fats INTEGER,
    carbs INTEGER,

    -- AI рекомендации
    ai_recommendations TEXT,
    ai_generated_at DATETIME,

    -- Анализ фото
    photo_analysis_count INTEGER DEFAULT 0,
    last_photo_id VARCHAR(200),

    -- Воронка
    funnel_status VARCHAR(20) DEFAULT 'new',
    drip_stage INTEGER DEFAULT 0,
    last_activity_at DATETIME,

    -- Timestamps
    created_at DATETIME,
    updated_at DATETIME,
    calculated_at DATETIME
);

-- Подписки
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,  -- FK → users.id
    plan VARCHAR(20),  -- 'monthly', 'yearly'
    status VARCHAR(20),  -- 'active', 'expired', 'cancelled'
    started_at DATETIME,
    expires_at DATETIME,
    payment_id VARCHAR(100),
    amount FLOAT,
    currency VARCHAR(10),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Анализы фото
CREATE TABLE photo_analyses (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    photo_file_id VARCHAR(200),
    body_fat_percentage FLOAT,
    muscle_mass_rating INTEGER,  -- 1-10
    body_type VARCHAR(50),  -- 'ectomorph', 'mesomorph', 'endomorph'
    analysis_result TEXT,  -- JSON с полным результатом
    created_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Изображения типов фигур (из roadmap.md)
CREATE TABLE body_type_images (
    id INTEGER PRIMARY KEY,
    gender VARCHAR(10),
    category VARCHAR(20),  -- 'current', 'target'
    type_number VARCHAR(5),
    file_id VARCHAR(200),
    caption VARCHAR(200),
    uploaded_at DATETIME,
    UNIQUE(gender, category, type_number)
);

-- Настройки бота (из roadmap.md)
CREATE TABLE bot_settings (
    id INTEGER PRIMARY KEY,
    key VARCHAR(100) UNIQUE,
    value TEXT,
    updated_at DATETIME
);
```

---

## 🎯 Флоу пользователя в едином боте

### Новый пользователь (Лид)
```
/start
  ↓
Лид-магнит опрос (из roadmap.md)
  ↓
Получает бесплатные рекомендации + КБЖУ
  ↓
Оффер: "Хочешь больше? Попробуй КБЖУ по фото!"
  ↓
[Кнопка: "Попробовать 7 дней бесплатно"]
```

### Платный клиент
```
/start (после оплаты подписки)
  ↓
Главное меню:
├─ 📸 Загрузить фото для анализа
├─ 📊 История анализов
├─ 💳 Управление подпиской
└─ 📞 Связаться с тренером
```

### Тренер (админ)
```
/start или /panel
  ↓
Меню тренера:
├─ 📋 Мои заявки (Mini App)
├─ 👥 Мои клиенты
├─ 📊 Статистика
└─ ⚙️ Настройки
```

---

## 🔐 Конфигурация (.env)

Добавить новые переменные:

```env
# Существующие (из текущего проекта)
TELEGRAM_BOT_TOKEN=your_token
ADMIN_CHAT_ID=123456789
N8N_WEBHOOK_URL=https://...
N8N_WEBHOOK_SECRET=secret

# НОВЫЕ: AI для анализа фото
OPENAI_API_KEY=sk-...
OPENAI_VISION_MODEL=gpt-4-vision-preview

# НОВЫЕ: OpenRouter для рекомендаций
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-4o-mini

# НОВЫЕ: Платежи
PAYMENT_PROVIDER=telegram_stars  # или 'stripe'
STRIPE_SECRET_KEY=sk_test_...  # если используем Stripe
STRIPE_PUBLISHABLE_KEY=pk_test_...

# НОВЫЕ: Mini App
MINI_APP_URL=https://your-domain.com/mini-app/

# НОВЫЕ: Подписка
MONTHLY_PRICE=990  # руб
YEARLY_PRICE=9900  # руб
TRIAL_DAYS=7
```

---

## 📈 Бизнес-метрики

После интеграции можно отслеживать:

1. **Конверсия лид → клиент:**
   - Сколько лидов из лид-магнита покупают подписку
   - Какие офферы работают лучше

2. **Retention (удержание):**
   - Сколько клиентов продлевают подписку
   - Частота использования анализа фото

3. **LTV (Lifetime Value):**
   - Средний доход с одного клиента
   - Окупаемость лид-магнита

4. **Эффективность тренера:**
   - Сколько лидов конвертируется в персональных клиентов
   - Время реакции на заявки через Mini App

---

## ⏱️ Общий timeline

| Фаза | Задачи | Время |
|------|--------|-------|
| 1 | Подготовка | 1 день |
| 2 | Реорганизация структуры | 2 дня |
| 3 | Расширение БД | 1 день |
| 4 | Режим "КБЖУ по фото" | 3 дня |
| 5 | Mini App | 3 дня |
| 6 | Единая точка входа | 1 день |
| 7 | Админ-панель | 2 дня |
| 8 | Тестирование | 2 дня |
| **Итого** | | **15 дней** |

---

## 🚀 Следующие шаги

### Вариант A: Начать с Mini App (быстрый старт)
1. Добавить Mini App в текущий проект (3 дня)
2. Протестировать панель тренера
3. Потом интегрировать КБЖУ по фото (5 дней)

### Вариант B: Полная интеграция сразу (15 дней)
1. Следовать плану миграции из Фазы 1-8
2. Получить полностью интегрированный продукт

### Вариант C: Микросервисы (для быстрого MVP)
1. Оставить текущий проект как лид-магнит
2. Создать отдельный бот для КБЖУ по фото (7 дней)
3. Добавить Mini App в текущий проект (3 дня)
4. Потом объединить (если нужно)

---

## 🎯 Моя рекомендация

**Вариант A (Mini App сначала):**

**Причины:**
1. ✅ Быстрый результат (3 дня)
2. ✅ Сразу получаешь панель тренера для работы с лидами
3. ✅ Минимальные изменения в текущем коде
4. ✅ Можно протестировать концепцию перед полной интеграцией
5. ✅ Если КБЖУ по фото еще не готов - не блокирует разработку

**План:**
1. **Неделя 1:** Добавить Mini App + новые поля из roadmap.md (3-4 дня)
2. **Неделя 2:** Протестировать с реальными лидами (2 дня)
3. **Неделя 3-4:** Интегрировать КБЖУ по фото если готов backend

---

## Вопросы для уточнения

1. **КБЖУ по фото проект:**
   - Уже есть рабочий backend?
   - На каком стеке написан? (Python/Node.js/другое)
   - Какой AI API используется? (OpenAI/Gemini/другое)

2. **Приоритеты:**
   - Что нужнее сейчас: Mini App или КБЖУ по фото?
   - Есть ли уже платящие клиенты в проекте с фото?

3. **Инфраструктура:**
   - Где хостится текущий бот?
   - Готов ли сервер для HTTPS (нужен для Mini App)?

Ответь на эти вопросы, и я предложу оптимальный план действий! 🚀

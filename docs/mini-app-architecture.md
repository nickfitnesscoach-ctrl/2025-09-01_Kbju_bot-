# Telegram Mini App: Панель тренера

## Обзор
Создание Telegram Mini App для управления заявками лидов, просмотра результатов опросов и AI-рекомендаций.

---

## Функционал Mini App

### 1. Главная страница
**Вкладки:**
- 📋 **Мои заявки** - список всех лидов
- ⚙️ **Настройки** (опционально, для будущего)

### 2. Страница "Мои заявки"

**Верхняя часть:**
- 🔗 **Ссылка на лид-магнит** - для распространения бота
  ```
  Разместить её в своих соц.сетях
  https://t.me/Fit_Coach_bot?start=edc149fb0a5e988e
  [Кнопка копирования]
  ```

**База лидов:**
- **Поиск по имени** (текстовое поле)
- **Список карточек лидов:**
  ```
  ┌─────────────────────────────────┐
  │ 👤 Артём Волков                 │
  │ @Zoomed67                       │
  │ Сегодня                         │
  │                                 │
  │ [👁 Подробнее]                  │
  └─────────────────────────────────┘
  ```

### 3. Карточка лида (детальная страница)

**Шапка:**
```
┌─────────────────────────────────┐
│     👤 Артём Волков             │
│        @Zoomed67                │
└─────────────────────────────────┘
```

**Кнопки действий:**
```
[💬 Написать в чат]  [👥 Сделать клиентом]
```

**Разделы информации:**

#### 📊 Основная информация
```
┌────────────────┬────────────────┬────────────────┐
│ Возраст: 21 лет│ Пол: Мужской   │ Рост: 166 см   │
├────────────────┴────────────────┴────────────────┤
│ Вес: 72 кг          │ Целевой вес: 50 кг         │
└─────────────────────┴─────────────────────────────┘
```

#### 🎯 Цель тренировок
```
┌─────────────────────────────────┐
│ Набрать массу                   │
└─────────────────────────────────┘
```

#### 📷 Фото и уровень жира
```
┌─────────────────────────────────┐
│ Текущая форма (~20%)            │
│                                 │
│     [ФОТО с номером 3]          │
│                                 │
│ Желаемая форма                  │
│                                 │
│     [ФОТО с номером 1]          │
└─────────────────────────────────┘
```

#### 🤖 Персонализированный ответ
```
┌─────────────────────────────────┐
│ Отлично! Вот что я могу сказать │
│ тебе:                           │
│                                 │
│ 📊 Анализ текущего состояния... │
│ 🎯 Безопасные цели...           │
│ 🎨 Ожидаемые изменения...       │
│ 🏋️ Целевые тренировки...        │
│ 🍽 Рамки по питанию...          │
└─────────────────────────────────┘
```

#### 🕐 Часовой пояс
```
┌─────────────────────────────────┐
│ UTC+3 (Europe/Moscow)           │
└─────────────────────────────────┘
```

#### 📊 КБЖУ (дополнительно)
```
┌─────────────────────────────────┐
│ 🔥 Калории: 2200 ккал           │
│ 🥩 Белки: 165 г                 │
│ 🥑 Жиры: 73 г                   │
│ 🍞 Углеводы: 220 г              │
└─────────────────────────────────┘
```

---

## Технологический стек

### Backend (Flask/FastAPI)
- **Framework:** Flask или FastAPI (рекомендую FastAPI для async)
- **База данных:** SQLite (уже используется)
- **API:** REST или JSON-RPC для Mini App

### Frontend (Telegram Mini App)
- **HTML5 + CSS3 + Vanilla JavaScript**
- **Telegram Web App API:** `window.Telegram.WebApp`
- **UI Framework:** Bootstrap 5 или Tailwind CSS (для быстрой разработки)
- **Альтернатива:** Vue.js/React (если нужна сложная логика)

### Преимущества простого стека (HTML+JS):
- ✅ Быстрая разработка
- ✅ Минимальная зависимость
- ✅ Легкая интеграция с Telegram WebApp API
- ✅ Не требует build процесса

---

## Архитектура проекта

### Структура папок

```
Калькулятор_КБЖУ_Лид_Магнит/
├── app/
│   ├── mini_app/                    # 🆕 Telegram Mini App
│   │   ├── __init__.py
│   │   ├── routes.py                # Flask/FastAPI роуты для API
│   │   ├── auth.py                  # Валидация Telegram InitData
│   │   └── static/                  # Статические файлы Mini App
│   │       ├── index.html           # Главная страница (список лидов)
│   │       ├── lead_detail.html     # Детальная страница лида
│   │       ├── css/
│   │       │   └── style.css        # Стили Mini App
│   │       └── js/
│   │           ├── app.js           # Главная логика
│   │           ├── telegram.js      # Telegram WebApp API wrapper
│   │           └── api.js           # API клиент
│   │
│   ├── admin_panel.py               # Существующая админ-панель
│   ├── webhook.py                   # Webhook для n8n
│   ├── handlers/                    # Telegram bot handlers
│   │   └── mini_app_handler.py      # 🆕 Handler для открытия Mini App
│   └── database/
│       ├── models.py                # Обновленные модели (новые поля)
│       └── requests.py              # CRUD операции
│
├── config.py                        # Добавить MINI_APP_URL
└── requirements.txt                 # Добавить cryptography для initData
```

---

## API Endpoints (Backend)

### Аутентификация
**POST `/mini-app/auth/validate`**
- Валидация Telegram initData
- Проверка, что пользователь = админ (ADMIN_TG_ID)
- Возврат JWT токена (опционально)

### Лиды
**GET `/mini-app/api/leads`**
- Получить список всех лидов
- Query params: `?search=имя` (поиск по имени/username)
- Response:
```json
{
  "leads": [
    {
      "id": 1,
      "tg_id": 123456789,
      "username": "Zoomed67",
      "first_name": "Артём",
      "last_name": "Волков",
      "created_at": "2025-01-12T10:30:00Z",
      "funnel_status": "calculated"
    }
  ]
}
```

**GET `/mini-app/api/leads/{lead_id}`**
- Получить детальную информацию о лиде
- Response:
```json
{
  "id": 1,
  "tg_id": 123456789,
  "username": "Zoomed67",
  "first_name": "Артём",
  "last_name": "Волков",
  "gender": "male",
  "age": 21,
  "height": 166,
  "weight": 72.0,
  "target_weight": 50.0,
  "current_body_type": "3",
  "target_body_type": "1",
  "activity": "moderate",
  "goal": "weight_gain",
  "timezone": "msk",
  "calories": 2200,
  "proteins": 165,
  "fats": 73,
  "carbs": 220,
  "ai_recommendations": "📊 Анализ текущего состояния...",
  "created_at": "2025-01-12T10:30:00Z"
}
```

### Изображения фигур
**GET `/mini-app/api/body-images/{gender}/{category}/{type_number}`**
- Получить file_id или прямую ссылку на изображение
- Params: `gender=male`, `category=current`, `type_number=3`
- Response:
```json
{
  "file_id": "AgACAgIAAxkBAAI...",
  "telegram_url": "https://api.telegram.org/file/bot{TOKEN}/photos/file_123.jpg",
  "caption": "Текущая форма (~20%)"
}
```

### Действия с лидом
**POST `/mini-app/api/leads/{lead_id}/message`**
- Открыть чат с лидом в Telegram
- Response: `{"chat_url": "https://t.me/{username}"}`

**POST `/mini-app/api/leads/{lead_id}/convert`**
- Пометить лида как клиента
- Обновить `funnel_status` на `client`

### Ссылка на лид-магнит
**GET `/mini-app/api/bot-link`**
- Получить реферальную ссылку бота
- Response:
```json
{
  "link": "https://t.me/Fit_Coach_bot?start=edc149fb0a5e988e",
  "qr_code": "data:image/png;base64,..." // опционально
}
```

---

## Frontend (Mini App)

### 1. index.html - Список лидов

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Панель тренера</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <div id="app">
        <!-- Заголовок -->
        <header>
            <h1>Панель тренера</h1>
        </header>

        <!-- Вкладки -->
        <nav class="tabs">
            <button class="tab active" data-tab="leads">
                👥 Заявки
            </button>
        </nav>

        <!-- Контент: Мои заявки -->
        <div id="leads-tab" class="tab-content active">
            <!-- Ссылка на лид-магнит -->
            <div class="lead-magnet">
                <p>Разместите её в своих соц.сетях</p>
                <div class="link-container">
                    <input type="text" id="bot-link" readonly value="https://t.me/Fit_Coach_bot?start=...">
                    <button id="copy-link">📋</button>
                </div>
            </div>

            <!-- Поиск -->
            <div class="search-bar">
                <input type="text" id="search" placeholder="🔍 Поиск по имени">
            </div>

            <!-- Список лидов -->
            <div id="leads-list" class="leads-list">
                <!-- Динамически генерируется через JS -->
            </div>
        </div>
    </div>

    <script src="js/telegram.js"></script>
    <script src="js/api.js"></script>
    <script src="js/app.js"></script>
</body>
</html>
```

### 2. lead_detail.html - Карточка лида

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Результаты опроса</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <div id="app">
        <!-- Кнопка назад -->
        <button id="back-btn" class="back-btn">← Назад</button>

        <!-- Шапка -->
        <div class="lead-header">
            <div class="avatar">👤</div>
            <h2 id="lead-name">Артём Волков</h2>
            <p id="lead-username">@Zoomed67</p>
        </div>

        <!-- Кнопки действий -->
        <div class="action-buttons">
            <button id="message-btn" class="btn btn-primary">
                💬 Написать в чат
            </button>
            <button id="convert-btn" class="btn btn-secondary">
                👥 Сделать клиентом
            </button>
        </div>

        <!-- Основная информация -->
        <section class="info-section">
            <h3>Основная информация</h3>
            <div class="info-grid">
                <div class="info-item">
                    <span class="label">Возраст:</span>
                    <span id="age">21 лет</span>
                </div>
                <div class="info-item">
                    <span class="label">Пол:</span>
                    <span id="gender">Мужской</span>
                </div>
                <div class="info-item">
                    <span class="label">Рост:</span>
                    <span id="height">166 см</span>
                </div>
                <div class="info-item">
                    <span class="label">Вес:</span>
                    <span id="weight">72 кг</span>
                </div>
                <div class="info-item">
                    <span class="label">Целевой вес:</span>
                    <span id="target-weight">50 кг</span>
                </div>
            </div>
        </section>

        <!-- Цель тренировок -->
        <section class="info-section">
            <h3>Цель тренировок</h3>
            <div class="goal-box" id="goal">Набрать массу</div>
        </section>

        <!-- Фото и уровень жира -->
        <section class="info-section">
            <h3>Фото и уровень жира</h3>
            <div class="body-photos">
                <div class="photo-item">
                    <p>Текущая форма (~20%)</p>
                    <img id="current-body-photo" src="" alt="Текущая фигура">
                </div>
                <div class="photo-item">
                    <p>Желаемая форма</p>
                    <img id="target-body-photo" src="" alt="Желаемая фигура">
                </div>
            </div>
        </section>

        <!-- AI рекомендации -->
        <section class="info-section">
            <h3>Персонализированный ответ</h3>
            <div class="ai-response" id="ai-recommendations">
                <!-- Динамически заполняется -->
            </div>
        </section>

        <!-- КБЖУ -->
        <section class="info-section">
            <h3>Рекомендации КБЖУ</h3>
            <div class="kbju-grid">
                <div class="kbju-item">
                    <span class="emoji">🔥</span>
                    <span class="value" id="calories">2200</span>
                    <span class="label">ккал</span>
                </div>
                <div class="kbju-item">
                    <span class="emoji">🥩</span>
                    <span class="value" id="proteins">165</span>
                    <span class="label">г белков</span>
                </div>
                <div class="kbju-item">
                    <span class="emoji">🥑</span>
                    <span class="value" id="fats">73</span>
                    <span class="label">г жиров</span>
                </div>
                <div class="kbju-item">
                    <span class="emoji">🍞</span>
                    <span class="value" id="carbs">220</span>
                    <span class="label">г углеводов</span>
                </div>
            </div>
        </section>

        <!-- Часовой пояс -->
        <section class="info-section">
            <h3>Часовой пояс</h3>
            <div class="timezone-box" id="timezone">UTC+3 (Europe/Moscow)</div>
        </section>
    </div>

    <script src="js/telegram.js"></script>
    <script src="js/api.js"></script>
    <script src="js/lead-detail.js"></script>
</body>
</html>
```

### 3. JavaScript файлы

#### telegram.js - Wrapper для Telegram WebApp API

```javascript
// telegram.js
class TelegramApp {
    constructor() {
        this.tg = window.Telegram.WebApp;
        this.tg.ready();
        this.tg.expand();

        // Применяем тему Telegram
        this.applyTheme();
    }

    applyTheme() {
        const bgColor = this.tg.themeParams.bg_color || '#ffffff';
        const textColor = this.tg.themeParams.text_color || '#000000';

        document.body.style.backgroundColor = bgColor;
        document.body.style.color = textColor;
    }

    getInitData() {
        return this.tg.initData;
    }

    getUserId() {
        return this.tg.initDataUnsafe?.user?.id;
    }

    showAlert(message) {
        this.tg.showAlert(message);
    }

    showConfirm(message, callback) {
        this.tg.showConfirm(message, callback);
    }

    close() {
        this.tg.close();
    }

    openLink(url) {
        this.tg.openLink(url);
    }

    // Кнопка "Назад"
    showBackButton(callback) {
        this.tg.BackButton.show();
        this.tg.BackButton.onClick(callback);
    }

    hideBackButton() {
        this.tg.BackButton.hide();
    }
}

const telegram = new TelegramApp();
```

#### api.js - API клиент

```javascript
// api.js
const API_BASE = '/mini-app/api';

class ApiClient {
    constructor() {
        this.initData = telegram.getInitData();
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': this.initData,
            ...options.headers
        };

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            telegram.showAlert('Ошибка загрузки данных');
            throw error;
        }
    }

    // Получить список лидов
    async getLeads(search = '') {
        const query = search ? `?search=${encodeURIComponent(search)}` : '';
        return this.request(`/leads${query}`);
    }

    // Получить детали лида
    async getLeadDetail(leadId) {
        return this.request(`/leads/${leadId}`);
    }

    // Получить ссылку на бота
    async getBotLink() {
        return this.request('/bot-link');
    }

    // Открыть чат с лидом
    async openChat(leadId) {
        return this.request(`/leads/${leadId}/message`, {
            method: 'POST'
        });
    }

    // Конвертировать в клиента
    async convertToClient(leadId) {
        return this.request(`/leads/${leadId}/convert`, {
            method: 'POST'
        });
    }

    // Получить изображение фигуры
    async getBodyImage(gender, category, typeNumber) {
        return this.request(`/body-images/${gender}/${category}/${typeNumber}`);
    }
}

const api = new ApiClient();
```

#### app.js - Главная страница (список лидов)

```javascript
// app.js
document.addEventListener('DOMContentLoaded', async () => {
    await loadBotLink();
    await loadLeads();

    // Поиск
    document.getElementById('search').addEventListener('input', debounce(async (e) => {
        await loadLeads(e.target.value);
    }, 300));

    // Копирование ссылки
    document.getElementById('copy-link').addEventListener('click', () => {
        const link = document.getElementById('bot-link');
        link.select();
        document.execCommand('copy');
        telegram.showAlert('Ссылка скопирована!');
    });
});

async function loadBotLink() {
    try {
        const data = await api.getBotLink();
        document.getElementById('bot-link').value = data.link;
    } catch (error) {
        console.error('Failed to load bot link:', error);
    }
}

async function loadLeads(search = '') {
    try {
        const data = await api.getLeads(search);
        renderLeads(data.leads);
    } catch (error) {
        console.error('Failed to load leads:', error);
    }
}

function renderLeads(leads) {
    const container = document.getElementById('leads-list');

    if (leads.length === 0) {
        container.innerHTML = '<p class="no-results">Заявок не найдено</p>';
        return;
    }

    container.innerHTML = leads.map(lead => `
        <div class="lead-card" onclick="openLeadDetail(${lead.id})">
            <div class="lead-info">
                <h3>${lead.first_name} ${lead.last_name || ''}</h3>
                <p class="username">@${lead.username || 'без username'}</p>
                <p class="date">${formatDate(lead.created_at)}</p>
            </div>
            <button class="btn-detail">👁 Подробнее</button>
        </div>
    `).join('');
}

function openLeadDetail(leadId) {
    window.location.href = `lead_detail.html?id=${leadId}`;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const today = new Date();

    if (date.toDateString() === today.toDateString()) {
        return 'Сегодня';
    }

    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === yesterday.toDateString()) {
        return 'Вчера';
    }

    return date.toLocaleDateString('ru-RU');
}

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}
```

#### lead-detail.js - Детальная страница лида

```javascript
// lead-detail.js
document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const leadId = urlParams.get('id');

    if (!leadId) {
        telegram.showAlert('Лид не найден');
        window.location.href = 'index.html';
        return;
    }

    // Кнопка "Назад"
    telegram.showBackButton(() => {
        window.location.href = 'index.html';
    });

    await loadLeadDetail(leadId);

    // Кнопка "Написать в чат"
    document.getElementById('message-btn').addEventListener('click', async () => {
        try {
            const data = await api.openChat(leadId);
            telegram.openLink(data.chat_url);
        } catch (error) {
            telegram.showAlert('Не удалось открыть чат');
        }
    });

    // Кнопка "Сделать клиентом"
    document.getElementById('convert-btn').addEventListener('click', () => {
        telegram.showConfirm('Пометить как клиента?', async (confirmed) => {
            if (confirmed) {
                try {
                    await api.convertToClient(leadId);
                    telegram.showAlert('Лид конвертирован в клиента!');
                } catch (error) {
                    telegram.showAlert('Ошибка конвертации');
                }
            }
        });
    });
});

async function loadLeadDetail(leadId) {
    try {
        const lead = await api.getLeadDetail(leadId);
        renderLeadDetail(lead);
    } catch (error) {
        telegram.showAlert('Ошибка загрузки данных лида');
        window.location.href = 'index.html';
    }
}

async function renderLeadDetail(lead) {
    // Шапка
    document.getElementById('lead-name').textContent =
        `${lead.first_name} ${lead.last_name || ''}`;
    document.getElementById('lead-username').textContent =
        `@${lead.username || 'без username'}`;

    // Основная информация
    document.getElementById('age').textContent = `${lead.age} лет`;
    document.getElementById('gender').textContent =
        lead.gender === 'male' ? 'Мужской' : 'Женский';
    document.getElementById('height').textContent = `${lead.height} см`;
    document.getElementById('weight').textContent = `${lead.weight} кг`;
    document.getElementById('target-weight').textContent = `${lead.target_weight} кг`;

    // Цель
    const goals = {
        'weight_loss': 'Похудеть',
        'weight_gain': 'Набрать массу',
        'maintenance': 'Поддержание веса'
    };
    document.getElementById('goal').textContent = goals[lead.goal] || lead.goal;

    // Фото фигур
    await loadBodyPhotos(lead);

    // AI рекомендации
    document.getElementById('ai-recommendations').innerHTML =
        formatAIRecommendations(lead.ai_recommendations);

    // КБЖУ
    document.getElementById('calories').textContent = lead.calories;
    document.getElementById('proteins').textContent = lead.proteins;
    document.getElementById('fats').textContent = lead.fats;
    document.getElementById('carbs').textContent = lead.carbs;

    // Часовой пояс
    const timezones = {
        'msk': 'UTC+3 (Москва)',
        'spb': 'UTC+3 (Санкт-Петербург)',
        'nsk': 'UTC+7 (Новосибирск)',
        // ... остальные
    };
    document.getElementById('timezone').textContent =
        timezones[lead.timezone] || lead.timezone;
}

async function loadBodyPhotos(lead) {
    try {
        // Текущая фигура
        const currentPhoto = await api.getBodyImage(
            lead.gender,
            'current',
            lead.current_body_type
        );
        document.getElementById('current-body-photo').src = currentPhoto.telegram_url;

        // Желаемая фигура
        const targetPhoto = await api.getBodyImage(
            lead.gender,
            'target',
            lead.target_body_type
        );
        document.getElementById('target-body-photo').src = targetPhoto.telegram_url;
    } catch (error) {
        console.error('Failed to load body photos:', error);
    }
}

function formatAIRecommendations(text) {
    if (!text) return '<p>Рекомендации не сгенерированы</p>';

    // Преобразуем markdown-like форматирование в HTML
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}
```

---

## Backend Implementation (Flask)

### app/mini_app/routes.py

```python
from flask import Blueprint, jsonify, request, send_from_directory
from app.database.requests import get_all_users, get_user
from app.mini_app.auth import validate_telegram_init_data
from config import ADMIN_TG_ID, TOKEN

mini_app_bp = Blueprint('mini_app', __name__, url_prefix='/mini-app')

# Статические файлы
@mini_app_bp.route('/')
def index():
    return send_from_directory('mini_app/static', 'index.html')

@mini_app_bp.route('/<path:path>')
def static_files(path):
    return send_from_directory('mini_app/static', path)

# API: Валидация
@mini_app_bp.route('/api/validate', methods=['POST'])
def validate_init_data():
    init_data = request.headers.get('X-Telegram-Init-Data')

    if not validate_telegram_init_data(init_data, TOKEN):
        return jsonify({'error': 'Invalid init data'}), 403

    # Проверка, что пользователь = админ
    user_id = extract_user_id_from_init_data(init_data)
    if user_id != ADMIN_TG_ID:
        return jsonify({'error': 'Access denied'}), 403

    return jsonify({'success': True})

# API: Список лидов
@mini_app_bp.route('/api/leads')
async def get_leads():
    search = request.args.get('search', '')
    users = await get_all_users(search_query=search)

    leads = [
        {
            'id': u.id,
            'tg_id': u.tg_id,
            'username': u.username,
            'first_name': u.first_name,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'funnel_status': u.funnel_status
        }
        for u in users
    ]

    return jsonify({'leads': leads})

# API: Детали лида
@mini_app_bp.route('/api/leads/<int:lead_id>')
async def get_lead_detail(lead_id):
    user = await get_user(lead_id)

    if not user:
        return jsonify({'error': 'Lead not found'}), 404

    return jsonify({
        'id': user.id,
        'tg_id': user.tg_id,
        'username': user.username,
        'first_name': user.first_name,
        'gender': user.gender,
        'age': user.age,
        'height': user.height,
        'weight': user.weight,
        'target_weight': user.target_weight,
        'current_body_type': user.current_body_type,
        'target_body_type': user.target_body_type,
        'activity': user.activity,
        'goal': user.goal,
        'timezone': user.timezone,
        'calories': user.calories,
        'proteins': user.proteins,
        'fats': user.fats,
        'carbs': user.carbs,
        'ai_recommendations': user.ai_recommendations,
        'created_at': user.created_at.isoformat() if user.created_at else None
    })

# API: Ссылка на бота
@mini_app_bp.route('/api/bot-link')
def get_bot_link():
    # Генерируем реферальную ссылку
    ref_code = generate_referral_code(ADMIN_TG_ID)
    link = f"https://t.me/Fit_Coach_bot?start={ref_code}"

    return jsonify({'link': link})

# API: Открыть чат
@mini_app_bp.route('/api/leads/<int:lead_id>/message', methods=['POST'])
async def open_chat(lead_id):
    user = await get_user(lead_id)

    if not user:
        return jsonify({'error': 'Lead not found'}), 404

    if user.username:
        chat_url = f"https://t.me/{user.username}"
    else:
        chat_url = f"tg://user?id={user.tg_id}"

    return jsonify({'chat_url': chat_url})

# API: Конвертировать в клиента
@mini_app_bp.route('/api/leads/<int:lead_id>/convert', methods=['POST'])
async def convert_to_client(lead_id):
    user = await get_user(lead_id)

    if not user:
        return jsonify({'error': 'Lead not found'}), 404

    user.funnel_status = 'client'
    await update_user(user)

    return jsonify({'success': True})

# API: Изображения фигур
@mini_app_bp.route('/api/body-images/<gender>/<category>/<type_number>')
async def get_body_image(gender, category, type_number):
    from app.database.requests import get_body_type_image

    image = await get_body_type_image(gender, category, type_number)

    if not image:
        return jsonify({'error': 'Image not found'}), 404

    # Генерируем Telegram URL (через Bot API)
    telegram_url = f"https://api.telegram.org/file/bot{TOKEN}/{image.file_id}"

    return jsonify({
        'file_id': image.file_id,
        'telegram_url': telegram_url,
        'caption': image.caption
    })


def generate_referral_code(admin_id):
    """Генерация реферального кода"""
    import hashlib
    data = f"{admin_id}{TOKEN}".encode()
    return hashlib.md5(data).hexdigest()[:16]

def extract_user_id_from_init_data(init_data):
    """Извлечь user_id из initData"""
    from urllib.parse import parse_qs
    params = parse_qs(init_data)
    user_json = params.get('user', [None])[0]
    if user_json:
        import json
        user = json.loads(user_json)
        return user.get('id')
    return None
```

### app/mini_app/auth.py - Валидация Telegram initData

```python
import hmac
import hashlib
from urllib.parse import parse_qs

def validate_telegram_init_data(init_data: str, bot_token: str) -> bool:
    """
    Валидация initData от Telegram WebApp
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = parse_qs(init_data)

        # Получаем hash
        received_hash = parsed.pop('hash', [None])[0]
        if not received_hash:
            return False

        # Собираем data_check_string
        data_check_arr = []
        for key in sorted(parsed.keys()):
            values = parsed[key]
            for value in values:
                data_check_arr.append(f"{key}={value}")

        data_check_string = '\n'.join(data_check_arr)

        # Вычисляем secret_key
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256
        ).digest()

        # Вычисляем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return calculated_hash == received_hash

    except Exception as e:
        print(f"Validation error: {e}")
        return False
```

---

## Telegram Bot Handler для открытия Mini App

### app/handlers/mini_app_handler.py

```python
from aiogram import Router, types
from aiogram.filters import Command
from config import MINI_APP_URL

router = Router()

@router.message(Command("panel"))
async def open_mini_app(message: types.Message):
    """Открыть панель тренера (только для админа)"""

    if message.from_user.id != ADMIN_TG_ID:
        await message.answer("У вас нет доступа к панели тренера")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text="📊 Открыть панель тренера",
            web_app=types.WebAppInfo(url=MINI_APP_URL)
        )]
    ])

    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть панель тренера:",
        reply_markup=keyboard
    )
```

---

## CSS (style.css)

```css
/* style.css */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    padding: 16px;
    background-color: var(--tg-theme-bg-color, #ffffff);
    color: var(--tg-theme-text-color, #000000);
}

/* Заголовки */
header {
    text-align: center;
    margin-bottom: 20px;
}

h1 {
    font-size: 24px;
    font-weight: 600;
}

h2 {
    font-size: 20px;
    font-weight: 600;
}

h3 {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 12px;
}

/* Вкладки */
.tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    border-bottom: 1px solid #e0e0e0;
}

.tab {
    flex: 1;
    padding: 12px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 16px;
    cursor: pointer;
    transition: all 0.3s;
}

.tab.active {
    border-bottom-color: var(--tg-theme-button-color, #3390ec);
    color: var(--tg-theme-button-color, #3390ec);
}

/* Лид-магнит */
.lead-magnet {
    background: #f5f5f5;
    padding: 16px;
    border-radius: 12px;
    margin-bottom: 20px;
}

.link-container {
    display: flex;
    gap: 8px;
}

.link-container input {
    flex: 1;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 14px;
}

.link-container button {
    padding: 10px 16px;
    background: var(--tg-theme-button-color, #3390ec);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 18px;
}

/* Поиск */
.search-bar {
    margin-bottom: 20px;
}

.search-bar input {
    width: 100%;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 16px;
}

/* Список лидов */
.leads-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.lead-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    transition: box-shadow 0.3s;
}

.lead-card:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.lead-info h3 {
    font-size: 18px;
    margin-bottom: 4px;
}

.username {
    color: #888;
    font-size: 14px;
}

.date {
    color: #888;
    font-size: 12px;
    margin-top: 4px;
}

.btn-detail {
    padding: 8px 16px;
    background: var(--tg-theme-button-color, #3390ec);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
}

/* Кнопка назад */
.back-btn {
    margin-bottom: 16px;
    padding: 8px 16px;
    background: #f5f5f5;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 16px;
}

/* Шапка лида */
.lead-header {
    text-align: center;
    margin-bottom: 20px;
    padding: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 12px;
}

.avatar {
    font-size: 48px;
    margin-bottom: 8px;
}

/* Кнопки действий */
.action-buttons {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
}

.btn {
    flex: 1;
    padding: 12px;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
    transition: opacity 0.3s;
}

.btn:hover {
    opacity: 0.8;
}

.btn-primary {
    background: var(--tg-theme-button-color, #3390ec);
    color: white;
}

.btn-secondary {
    background: #f5f5f5;
    color: #333;
}

/* Секции информации */
.info-section {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
}

.info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
}

.info-item {
    padding: 12px;
    background: #f5f5f5;
    border-radius: 8px;
}

.info-item .label {
    color: #888;
    font-size: 14px;
    display: block;
    margin-bottom: 4px;
}

/* Цель */
.goal-box {
    padding: 16px;
    background: #e3f2fd;
    border-radius: 8px;
    text-align: center;
    font-size: 18px;
    color: #1976d2;
}

/* Фото фигур */
.body-photos {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.photo-item {
    text-align: center;
}

.photo-item img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin-top: 8px;
}

/* AI рекомендации */
.ai-response {
    padding: 16px;
    background: #f0f7ff;
    border-left: 4px solid #3390ec;
    border-radius: 8px;
    line-height: 1.8;
}

/* КБЖУ */
.kbju-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
}

.kbju-item {
    text-align: center;
    padding: 16px;
    background: #f5f5f5;
    border-radius: 8px;
}

.kbju-item .emoji {
    font-size: 32px;
    display: block;
    margin-bottom: 8px;
}

.kbju-item .value {
    font-size: 24px;
    font-weight: 600;
    display: block;
    margin-bottom: 4px;
}

.kbju-item .label {
    font-size: 14px;
    color: #888;
}

/* Часовой пояс */
.timezone-box {
    padding: 16px;
    background: #f5f5f5;
    border-radius: 8px;
    text-align: center;
    font-size: 16px;
}

/* Нет результатов */
.no-results {
    text-align: center;
    color: #888;
    padding: 40px 20px;
}
```

---

## Конфигурация (config.py)

Добавить:

```python
# Mini App URL
MINI_APP_URL = os.getenv('MINI_APP_URL', 'https://your-domain.com/mini-app/')
```

---

## Зависимости (requirements.txt)

Добавить:

```
cryptography>=41.0.0  # для валидации initData
```

---

## План реализации

### Этап 1: Backend API (2-3 дня)
- [ ] Создать структуру папок `app/mini_app/`
- [ ] Реализовать `routes.py` (все API endpoints)
- [ ] Реализовать `auth.py` (валидация initData)
- [ ] Добавить функции в `database/requests.py` для поиска лидов
- [ ] Протестировать API через Postman

### Этап 2: Frontend - Список лидов (2 дня)
- [ ] Создать `index.html` (главная страница)
- [ ] Создать `telegram.js` (wrapper для WebApp API)
- [ ] Создать `api.js` (API клиент)
- [ ] Создать `app.js` (логика списка лидов)
- [ ] Создать `style.css` (базовые стили)
- [ ] Протестировать в Telegram

### Этап 3: Frontend - Карточка лида (2 дня)
- [ ] Создать `lead_detail.html`
- [ ] Создать `lead-detail.js` (логика детальной страницы)
- [ ] Загрузка изображений фигур
- [ ] Форматирование AI-рекомендаций
- [ ] Кнопки действий (написать, конвертировать)
- [ ] Протестировать в Telegram

### Этап 4: Telegram Bot Integration (1 день)
- [ ] Создать `mini_app_handler.py`
- [ ] Добавить команду `/panel` для админа
- [ ] Кнопка открытия Mini App в inline клавиатуре
- [ ] Протестировать открытие из бота

### Этап 5: Тестирование и доработка (1-2 дня)
- [ ] End-to-end тестирование всех функций
- [ ] Проверка на разных устройствах (iOS, Android)
- [ ] Оптимизация производительности
- [ ] Обработка ошибок и edge cases
- [ ] Финальный UI polish

### Этап 6: Deploy (1 день)
- [ ] Настроить HTTPS для Mini App
- [ ] Зарегистрировать Mini App в BotFather
- [ ] Deploy на production сервер
- [ ] Финальное тестирование

**Общее время: 9-12 дней**

---

## Безопасность

### ✅ Валидация initData
- Проверка подписи через HMAC-SHA256
- Защита от подделки запросов

### ✅ Доступ только для админа
- Проверка `ADMIN_TG_ID` на каждом запросе
- Запрет доступа для обычных пользователей

### ✅ HTTPS обязателен
- Telegram требует HTTPS для Mini Apps
- Используйте Let's Encrypt или Cloudflare

### ✅ Rate limiting
- Ограничение запросов к API
- Защита от DDoS

---

## Следующие шаги

1. **Одобрить архитектуру** - подтвердить, что дизайн соответствует требованиям
2. **Выбрать технологии** - Flask или FastAPI для backend?
3. **Начать разработку** - с какого этапа начать? (рекомендую Этап 1: Backend API)

Готов приступать к разработке! 🚀

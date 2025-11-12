# Структура проекта

```
Калькулятор_КБЖУ_Лид_Магнит/
├── app/                          # Основное приложение
│   ├── admin_panel.py           # Flask админ-панель (с 2FA, rate limiting, security headers)
│   ├── webhook.py               # Webhook интеграция с n8n (обязательная аутентификация)
│   ├── handlers/                # Telegram bot handlers
│   ├── database/                # Модели и запросы к БД
│   └── texts_data.json          # Тексты бота
│
├── docs/                         # 📚 Документация
│   ├── 2fa-setup.md             # Инструкция по настройке 2FA
│   ├── https-setup.md           # Инструкция по настройке HTTPS с nginx
│   ├── security-audit.md        # Аудит безопасности
│   ├── security-fixes-report.md # Отчёт об исправлениях
│   ├── bugs.md                  # Известные баги
│   ├── README_DEV.md            # Документация для разработчиков
│   └── PROJECT_STRUCTURE.md     # Этот файл
│
├── tests/                        # 🧪 Тесты безопасности
│   ├── test_rate_limiting.py    # Тест rate limiting на логине
│   ├── test_security_headers.py # Тест security headers
│   ├── test_webhook_security.py # Тест webhook аутентификации
│   └── README.md                # Инструкция по запуску тестов
│
├── utils/                        # 🛠️ Утилиты
│   ├── generate_2fa_qr.py       # Генератор QR-кода для 2FA
│   ├── notifications.py         # Уведомления админу
│   └── smoke_polling.py         # Smoke тесты
│
├── templates/                    # HTML шаблоны Flask
│   ├── login.html               # Форма логина (с поддержкой 2FA)
│   ├── index.html               # Главная страница админ-панели
│   └── edit_text.html           # Редактирование текстов
│
├── data/                         # Данные
│   └── db.sqlite3               # SQLite база данных
│
├── config.py                     # ⚙️ Конфигурация проекта
├── requirements.txt              # Python зависимости
├── run.py                        # Запуск Telegram бота
├── start_admin_panel.py          # Запуск админ-панели
├── README.md                     # Основной README
├── docker-compose.yml            # Docker конфигурация
└── .env                          # Environment переменные (не в git)
```

## Ключевые файлы

### Конфигурация
- **config.py** - централизованная конфигурация, валидация webhook секретов
- **.env** - переменные окружения (пароли, токены, секреты)
- **requirements.txt** - Python зависимости включая `pyotp` и `qrcode` для 2FA

### Безопасность
- **app/admin_panel.py** - защищённая админ-панель с 2FA, rate limiting, security headers
- **tests/** - тесты безопасности (все проходят ✅)
- **docs/security-*.md** - документация по безопасности

### Telegram Bot
- **app/handlers/** - обработчики команд и сообщений
- **app/database/** - ORM модели и запросы
- **app/texts_data.json** - редактируемые тексты бота

## Быстрый старт

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка .env
```bash
cp .env.example .env
# Отредактируйте .env файл
```

### 3. Запуск бота
```bash
python run.py
```

### 4. Запуск админ-панели
```bash
python start_admin_panel.py
```

### 5. Запуск тестов
```bash
python tests/test_rate_limiting.py
python tests/test_security_headers.py
python tests/test_webhook_security.py
```

## Новые фичи безопасности

### ✅ Two-Factor Authentication (2FA)
- TOTP поддержка (Google Authenticator, Authy)
- Опциональная настройка через `ENABLE_2FA=True`
- См. [docs/2fa-setup.md](2fa-setup.md)

### ✅ Rate Limiting
- 5 попыток логина в минуту
- Глобальные лимиты: 200/день, 50/час
- Защита от brute-force

### ✅ HTTPS Support
- Secure cookie flags
- HSTS headers
- Session timeout (1 час)
- См. [docs/https-setup.md](https-setup.md)

### ✅ Security Headers
- Content-Security-Policy
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy
- Permissions-Policy

### ✅ Webhook Authentication
- Обязательный `N8N_WEBHOOK_SECRET`
- Fail-fast при неверной конфигурации
- X-Webhook-Secret header

### ✅ File Upload Limits
- Максимум 20 MB
- MIME-type валидация
- HTTP 413 обработчик

## Документация

- [README.md](../README.md) - Основная документация
- [docs/README_DEV.md](README_DEV.md) - Для разработчиков
- [docs/2fa-setup.md](2fa-setup.md) - Настройка 2FA
- [docs/https-setup.md](https-setup.md) - Настройка HTTPS
- [docs/security-audit.md](security-audit.md) - Аудит безопасности
- [docs/security-fixes-report.md](security-fixes-report.md) - Отчёт об исправлениях

## Environment Variables

### Обязательные
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_PASSWORD_HASH=scrypt:...  # или ADMIN_PASSWORD
```

### Опциональные для безопасности
```bash
USE_HTTPS=True                   # Enable HTTPS mode
ENABLE_2FA=True                  # Enable Two-Factor Auth
TOTP_SECRET=YOUR_SECRET_HERE     # TOTP secret for 2FA
N8N_WEBHOOK_SECRET=secret        # Required if N8N_WEBHOOK_URL is set
```

### Другие опциональные
```bash
ADMIN_CHAT_ID=123456789
N8N_WEBHOOK_URL=https://...
ENABLE_SUBSCRIPTION_GATE=True
CHANNEL_URL=https://t.me/...
DEBUG=False
```

## Порты

- **8080** - Админ-панель Flask (рекомендуется за nginx reverse proxy)
- **Telegram** - Webhook или polling (настраивается)

## Deployment

Рекомендуется использовать:
1. **nginx** - reverse proxy для админ-панели
2. **Let's Encrypt** - бесплатные SSL сертификаты
3. **systemd** - для автозапуска сервисов
4. **gunicorn** - WSGI сервер вместо встроенного Flask

См. [docs/https-setup.md](https-setup.md) для подробных инструкций.

## Безопасность

### Risk Level
- **До исправлений**: MEDIUM (1 CRITICAL, 3 HIGH)
- **После исправлений**: LOW ✅ (0 CRITICAL, 0 HIGH)

### Рекомендации
1. ✅ Всегда используйте HTTPS в production
2. ✅ Включите 2FA для админ-панели
3. ✅ Настройте N8N_WEBHOOK_SECRET
4. ✅ Регулярно обновляйте зависимости
5. ✅ Мониторьте логи на подозрительную активность

## Контрибьюция

1. Создайте feature branch
2. Внесите изменения
3. Запустите тесты: `python tests/test_*.py`
4. Создайте Pull Request

## Лицензия

[Укажите лицензию проекта]

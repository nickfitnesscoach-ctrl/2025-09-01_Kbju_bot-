# aiogram_sqla_sample

Этот проект представляет собой пример Telegram-бота, разработанного с использованием фреймворка **aiogram** (v3) и библиотеки **SQLAlchemy** (v2) для асинхронных операций с базой данных.

## Основные функции

- Пользовательская часть через Telegram-бот
- Админ-панель с веб-интерфейсом для управления текстами бота
- Интеграция с n8n webhook
- Асинхронная работа с базой данных SQLite

## Технический стек

- Python 3.12
- aiogram 3.22.0
- SQLAlchemy 2.0.30
- Flask 3.0.3
- Gunicorn 22.0.0

## Установка и запуск

### Подготовка виртуального окружения

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Запуск Telegram-бота

```bash
python run.py
```

### Запуск веб-админ-панели

Существует несколько способов запуска админ-панели:

1. Через скрипт запуска (рекомендуется):
```bash
# Windows
python start_admin_panel.py

2. Напрямую из директории app:
```bash
cd app
python admin_panel.py
```

После запуска админ-панель будет доступна по адресу: http://localhost:8080

Для входа используйте пароль, указанный в файле `.env` в переменной `ADMIN_PASSWORD`. Если переменная не задана, используется пароль по умолчанию: `admin`

## Docker

Для запуска в Docker используйте:

```bash
docker-compose up -d
```

## Конфигурация

Создайте файл `.env` на основе `.env.example` и укажите необходимые параметры:

- `TOKEN` - токен Telegram-бота
- `ADMIN_PASSWORD` - пароль для доступа к админ-панели (по умолчанию: admin)
- `SECRET_KEY` - секретный ключ для Flask (по умолчанию: your-secret-key-here)
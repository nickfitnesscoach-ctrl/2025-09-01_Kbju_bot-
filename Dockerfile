# Dockerfile для продакшен деплоя
FROM python:3.13-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY . .

# Создание пользователя без привилегий
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# Команда запуска
CMD ["python", "run.py"]
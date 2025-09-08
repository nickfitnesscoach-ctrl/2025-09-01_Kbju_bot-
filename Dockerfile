# ---- Builder -----------------------------------------------------------------
    FROM python:3.12-slim-bookworm AS builder

    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        DEBIAN_FRONTEND=noninteractive
    
    WORKDIR /app
    
    # Минимальный набор для сборки
    RUN set -eux; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            gcc \
            libpq-dev \
        ; \
        rm -rf /var/lib/apt/lists/*
    
    # Устанавливаем зависимости
    COPY requirements.txt .
    RUN python -m venv /opt/venv && \
        /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
        /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
    
    # ---- Runtime -----------------------------------------------------------------
    FROM python:3.12-slim-bookworm
    
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        DEBIAN_FRONTEND=noninteractive \
        PYTHONPATH=/app \
        PATH=/opt/venv/bin:$PATH
    
    WORKDIR /app
    
    # Только runtime библиотеки
    RUN set -eux; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            libpq5 \
            ca-certificates \
        ; \
        rm -rf /var/lib/apt/lists/*
    
    # Копируем venv из builder
    COPY --from=builder /opt/venv /opt/venv
    
    # Копируем код
    COPY . .
    
    # Создаем config.py если его нет (исправленная версия)
    RUN if [ ! -f config.py ]; then \
        printf '%s\n' \
        'import os' \
        'def _b(v: str) -> bool: return str(v).lower() in ("1","true","yes","y","on")' \
        'TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN", "")' \
        'BOT_TOKEN = TOKEN' \
        'DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///db.sqlite3")' \
        'N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")' \
        'CHANNEL_URL = os.getenv("CHANNEL_URL", "")' \
        'DEBUG = _b(os.getenv("DEBUG", "false"))' \
        > config.py; \
        fi
    
    # Создаем пользователя и меняем права
    RUN useradd -r -u 1001 appuser && \
        chown -R appuser:appuser /app
    
    USER appuser
    
    CMD ["python", "run.py"]
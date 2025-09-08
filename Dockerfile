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
    apt-get install -y --no-install-recommends gcc; \
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
        ca-certificates \
        sqlite3 \
    ; \
    rm -rf /var/lib/apt/lists/*

# Пользователь до COPY, чтобы использовать --chown
RUN useradd -r -u 1001 appuser

# Копируем venv из builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Копируем код (сразу с владельцем)
COPY --chown=appuser:appuser . .

# Создаём каталоги данных/логов (вдруг volumes не примонтированы) и даём права
RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app/data /app/logs

# Создаём config.py если его нет (исправленный fallback DB_URL)
RUN if [ ! -f config.py ]; then \
    printf '%s\n' \
    'import os' \
    'def _b(v: str) -> bool: return str(v).lower() in ("1","true","yes","y","on")' \
    'TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN", "")' \
    'BOT_TOKEN = TOKEN' \
    'DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:////app/data/db.sqlite3")' \
    'N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")' \
    'CHANNEL_URL = os.getenv("CHANNEL_URL", "")' \
    'DEBUG = _b(os.getenv("DEBUG", "false"))' \
    > config.py; \
    fi

USER appuser

CMD ["python", "run.py"]
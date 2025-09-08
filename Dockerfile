# ---- Builder -----------------------------------------------------------------
    FROM python:3.12-slim-bookworm AS builder

    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        DEBIAN_FRONTEND=noninteractive
    
    WORKDIR /app
    
    # Тулчейн и dev-хедеры только для сборки зависимостей
    RUN set -eux; \
        echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80retries; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            build-essential gcc \
            libpq-dev libffi-dev libjpeg62-turbo-dev zlib1g-dev \
        ; \
        rm -rf /var/lib/apt/lists/*
    
    # Устанавливаем python-зависимости в отдельный venv
    COPY requirements.txt .
    RUN python -m venv /opt/venv \
     && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
     && /opt/venv/bin/pip install --no-cache-dir --prefer-binary -r requirements.txt
    
    # ---- Runtime -----------------------------------------------------------------
    FROM python:3.12-slim-bookworm AS runtime
    
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        DEBIAN_FRONTEND=noninteractive \
        PYTHONPATH=/app \
        PATH=/opt/venv/bin:$PATH
    
    WORKDIR /app
    
    # Только runtime-библиотеки (без *-dev)
    RUN set -eux; \
        echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80retries; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            libpq5 libffi8 libjpeg62-turbo zlib1g \
            ca-certificates curl \
        ; \
        rm -rf /var/lib/apt/lists/*
    
    # Забираем готовый venv из builder
    COPY --from=builder /opt/venv /opt/venv
    
    # Код приложения
    COPY . .
    
    # Конфиг-шим только если файла нет
    RUN test -f config.py || cat > config.py <<'PY'
    import os
    def _b(v: str) -> bool: return str(v).lower() in ("1","true","yes","y","on")
    TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN", "")
    BOT_TOKEN = TOKEN
    DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///db.sqlite3")
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
    CHANNEL_URL = os.getenv("CHANNEL_URL", "")
    DEBUG = _b(os.getenv("DEBUG", "false"))
    PY
    
    # Безопасность
    RUN useradd -r -u 1001 appuser && chown -R appuser:appuser /app
    USER appuser
    
    CMD ["python", "run.py"]
    
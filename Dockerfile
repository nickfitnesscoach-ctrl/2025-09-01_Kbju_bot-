# ---- Base (pin) --------------------------------------------------------------
# Было: python:3.12-slim  -> плавающий релиз. Фиксируем на стабильном bookworm.
FROM python:3.12-slim-bookworm

# Быстрый и предсказуемый Python в контейнере
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app

WORKDIR /app

# ---- System deps (устойчивее) ------------------------------------------------
# Добавлены:
#  - ca-certificates, curl: иногда APT/HTTPS ломается без них
#  - apt retries: чтобы не падать из-за разовых сетевых сбоев
RUN set -eux; \
    echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80retries; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    ; \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps --------------------------------------------------------------
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir --prefer-binary -r requirements.txt

# ---- App code -----------------------------------------------------------------
COPY . .

# ---- Config shim --------------------------------------------------------------
# Создаём config.py из ENV, только если файла нет в образе
RUN test -f config.py || cat > config.py <<'PY'
import os

def _b(v: str) -> bool:
    return str(v).lower() in ("1","true","yes","y","on")

TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN", "")
BOT_TOKEN = TOKEN

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///db.sqlite3")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
CHANNEL_URL = os.getenv("CHANNEL_URL", "")
DEBUG = _b(os.getenv("DEBUG", "false"))
PY


# ---- Security -----------------------------------------------------------------
RUN useradd -r -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# ---- Run ----------------------------------------------------------------------
CMD ["python", "run.py"]

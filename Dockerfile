# ---- Base --------------------------------------------------------------------
FROM python:3.12-slim

# Быстрый и предсказуемый Python в контейнере
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app

WORKDIR /app

# ---- System deps (минимум, но с запасом для частых пакетов) ------------------
# libpq-dev для psycopg2/asyncpg, libffi/openssl/jpeg/zlib для crypto/pillow и пр.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    libffi-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

# ---- Python deps --------------------------------------------------------------
# Сначала зависимости (лучше кэшируются), потом код
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

# ---- App code -----------------------------------------------------------------
COPY . .

# ---- Config shim --------------------------------------------------------------
# Если config.py отсутствует (например, игнорируется .dockerignore),
# создаём его из ENV. Совместимы оба имени токена: TOKEN и BOT_TOKEN.
RUN [ -f config.py ] || cat > config.py <<'PY'
import os

def _b(v: str) -> bool:
    return str(v).lower() in ("1","true","yes","y","on")

# Совместимость имён
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

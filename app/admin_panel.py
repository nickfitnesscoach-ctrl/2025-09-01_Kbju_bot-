"""Flask-based admin panel for managing bot texts."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from requests import RequestException
from werkzeug.security import check_password_hash, generate_password_hash

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for env_path in (PROJECT_ROOT / ".env", CURRENT_DIR / ".env"):
    load_dotenv(env_path, override=False)

from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN  # noqa: E402  pylint: disable=wrong-import-position

logger = logging.getLogger(__name__)

TEMPLATES_DIR = PROJECT_ROOT / "templates"
TEXTS_FILE = CURRENT_DIR / "texts_data.json"


def _load_secret_key() -> str:
    secret_key = os.getenv("SECRET_KEY")
    if secret_key:
        return secret_key

    generated = secrets.token_hex(32)
    logger.warning("SECRET_KEY is not set; generated ephemeral key for current session")
    return generated


def _load_password_hash() -> str:
    password_hash = os.getenv("ADMIN_PASSWORD_HASH")
    if password_hash:
        return password_hash

    plain_password = os.getenv("ADMIN_PASSWORD")
    if plain_password:
        logger.warning(
            "ADMIN_PASSWORD is configured in plaintext; hashing at runtime. "
            "Set ADMIN_PASSWORD_HASH to avoid storing secrets in clear text.",
        )
        return generate_password_hash(plain_password)

    raise RuntimeError(
        "Admin panel password is not configured. Set ADMIN_PASSWORD_HASH environment variable.",
    )


app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = _load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
csrf = CSRFProtect(app)

PASSWORD_HASH = _load_password_hash()


def load_texts() -> dict[str, Any]:
    """Load all bot texts from storage."""
    try:
        with TEXTS_FILE.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.warning("Texts file %s not found; returning empty mapping", TEXTS_FILE)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse texts file %s: %s", TEXTS_FILE, exc)
        raise RuntimeError("Файл текстов повреждён. Проверьте JSON.") from exc


def save_texts(texts: Mapping[str, Any]) -> None:
    """Persist bot texts to storage."""
    with TEXTS_FILE.open("w", encoding="utf-8") as fp:
        json.dump(texts, fp, ensure_ascii=False, indent=2)


def _extract_file_id(media_type: str, result_payload: Any) -> str | None:
    """Получить file_id из ответа Telegram в зависимости от типа медиа."""

    if not isinstance(result_payload, dict):
        return None

    if media_type == "photo":
        photos = result_payload.get("photo")
        if isinstance(photos, list) and photos:
            last_photo = photos[-1]
            if isinstance(last_photo, dict):
                file_id = last_photo.get("file_id")
                if isinstance(file_id, str):
                    return file_id
        return None

    video = result_payload.get("video")
    if isinstance(video, dict):
        file_id = video.get("file_id")
        if isinstance(file_id, str):
            return file_id
    return None


def login_required(func):
    """Ensure the user is authenticated before accessing the view."""

    @wraps(func)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return decorated_function


@app.route("/")
@login_required
def index():
    texts = load_texts()
    return render_template("index.html", texts=texts)


def _verify_password(password: str) -> bool:
    return check_password_hash(PASSWORD_HASH, password)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if _verify_password(password):
            session["authenticated"] = True
            session.permanent = False
            return redirect(url_for("index"))

        logger.info("Failed admin login attempt")
        flash("Неверный пароль", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


def _get_telegram_file_url(file_id: str | None) -> str | None:
    """Resolve direct download URL for a Telegram file."""

    if not file_id or not TELEGRAM_BOT_TOKEN:
        return None

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"

    try:
        response = requests.get(endpoint, params={"file_id": file_id}, timeout=15)
    except RequestException as exc:
        logger.debug("Failed to fetch file path for %s: %s", file_id, exc)
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.debug("Telegram getFile returned non-JSON response for %s", file_id)
        return None

    if not response.ok or not payload.get("ok"):
        logger.debug("Telegram getFile failed for %s: %s", file_id, payload)
        return None

    result = payload.get("result")
    if not isinstance(result, dict):
        return None

    file_path = result.get("file_path")
    if not isinstance(file_path, str):
        return None

    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"


def _resolve_nested_value(texts: Mapping[str, Any], key_path: Iterable[str]) -> Any:
    value: Any = texts
    for key in key_path:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


@app.route("/edit/<path:text_key>")
@login_required
def edit_text(text_key: str):
    texts = load_texts()
    keys = text_key.split(".") if text_key else []
    value = _resolve_nested_value(texts, keys)

    if value is None:
        flash("Указанный ключ не найден в JSON.", "error")
        return redirect(url_for("index"))

    photo_preview_url = None
    video_preview_url = None

    if isinstance(value, dict):
        photo_preview_url = _get_telegram_file_url(value.get("photo_file_id"))
        video_preview_url = _get_telegram_file_url(value.get("video_file_id"))

    return render_template(
        "edit_text.html",
        text_key=text_key,
        text_data=value,
        photo_preview_url=photo_preview_url,
        video_preview_url=video_preview_url,
    )


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


@app.route("/save_text", methods=["POST"])
@login_required
def save_text():
    text_key = request.form.get("text_key")
    if not text_key:
        abort(400, "text_key is required")

    text_content = request.form.get("text_content", "")
    is_message = request.form.get("is_message") == "1"
    photo_file_id = request.form.get("photo_file_id", "").strip()
    video_file_id = request.form.get("video_file_id", "").strip()

    texts = load_texts()
    keys = text_key.split(".")
    current: dict[str, Any] = texts

    for key in keys[:-1]:
        current = _ensure_dict(current, key)

    target_key = keys[-1]

    if is_message:
        target = current.get(target_key)
        if not isinstance(target, dict):
            target = {}

        target["text"] = text_content

        if photo_file_id:
            target["photo_file_id"] = photo_file_id
        else:
            target.pop("photo_file_id", None)

        if video_file_id:
            target["video_file_id"] = video_file_id
        else:
            target.pop("video_file_id", None)

        current[target_key] = target
    else:
        current[target_key] = text_content

    save_texts(texts)
    flash("Текст успешно сохранен", "success")
    return redirect(url_for("index"))


@app.route("/upload_media", methods=["POST"])
@login_required
def upload_media():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Cannot upload media: TELEGRAM_BOT_TOKEN is not configured")
        return (
            jsonify({"ok": False, "error": "Не настроен токен бота для загрузки файлов."}),
            500,
        )

    if ADMIN_CHAT_ID is None:
        logger.error("Cannot upload media: ADMIN_CHAT_ID is not configured")
        return (
            jsonify({"ok": False, "error": "Не указан ADMIN_CHAT_ID для загрузки файлов."}),
            500,
        )

    media_type = request.form.get("media_type", "")
    if media_type not in {"photo", "video"}:
        return jsonify({"ok": False, "error": "Неверный тип медиа."}), 400

    file = request.files.get("media")
    if file is None or not file.filename:
        return jsonify({"ok": False, "error": "Выберите файл для загрузки."}), 400

    telegram_method = "sendPhoto" if media_type == "photo" else "sendVideo"
    telegram_field = "photo" if media_type == "photo" else "video"
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{telegram_method}"

    if hasattr(file, "stream"):
        try:
            file.stream.seek(0)
        except OSError:
            logger.debug("Unable to seek upload stream for %s", file.filename)

    files = {
        telegram_field: (
            file.filename or f"{media_type}.bin",
            file.stream,
            file.mimetype or "application/octet-stream",
        )
    }
    data = {
        "chat_id": str(ADMIN_CHAT_ID),
        "disable_notification": "true",
    }

    try:
        response = requests.post(endpoint, data=data, files=files, timeout=30)
    except RequestException as exc:
        logger.error("Failed to send %s to Telegram: %s", media_type, exc)
        return (
            jsonify({"ok": False, "error": "Не удалось загрузить файл. Попробуйте позже."}),
            502,
        )

    try:
        payload = response.json()
    except ValueError:
        logger.error(
            "Telegram response for %s is not JSON. Status: %s",
            telegram_method,
            response.status_code,
        )
        return (
            jsonify({"ok": False, "error": "Telegram вернул некорректный ответ."}),
            502,
        )

    if not response.ok or not payload.get("ok"):
        description = payload.get("description") if isinstance(payload, dict) else None
        logger.error(
            "Telegram %s failed: status=%s, payload=%s",
            telegram_method,
            response.status_code,
            payload,
        )
        message = "Не удалось загрузить файл в Telegram."
        if description:
            message = f"{message} {description}"
        return jsonify({"ok": False, "error": message}), 502

    file_id = _extract_file_id(media_type, payload.get("result"))
    if not file_id:
        logger.error(
            "Could not extract file_id from Telegram %s response: %s",
            telegram_method,
            payload,
        )
        return (
            jsonify({"ok": False, "error": "Не удалось получить file_id из ответа Telegram."}),
            502,
        )

    preview_url = _get_telegram_file_url(file_id)

    logger.info(
        "Uploaded %s for text '%s' with file_id=%s",
        media_type,
        request.form.get("text_key", "<unknown>"),
        file_id,
    )

    return jsonify(
        {
            "ok": True,
            "file_id": file_id,
            "media_type": media_type,
            "preview_url": preview_url,
        }
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

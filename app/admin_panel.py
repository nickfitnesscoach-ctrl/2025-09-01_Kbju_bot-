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

import pyotp
import qrcode
import qrcode.image.svg
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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


def _load_2fa_config() -> tuple[bool, str | None]:
    """Load 2FA configuration from environment.

    Returns:
        (enabled, totp_secret): Tuple with 2FA status and TOTP secret if enabled
    """
    enable_2fa = os.getenv("ENABLE_2FA", "False").lower() in ("true", "1", "yes")

    if not enable_2fa:
        return False, None

    totp_secret = os.getenv("TOTP_SECRET")
    if not totp_secret or not totp_secret.strip():
        logger.warning(
            "ENABLE_2FA is True but TOTP_SECRET is not configured. "
            "2FA will be disabled. Generate a secret with: python -c 'import pyotp; print(pyotp.random_base32())'"
        )
        return False, None

    logger.info("Two-Factor Authentication (2FA) is ENABLED for admin panel")
    return True, totp_secret


app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = _load_secret_key()

# Security: Check if running in production mode (HTTPS expected)
USE_HTTPS = os.getenv("USE_HTTPS", "False").lower() in ("true", "1", "yes")

# Security: Limit file upload size to prevent DoS
# Telegram limits: 20MB for photos, 50MB for videos
# Setting 20MB as conservative limit (can be increased if needed)
MAX_FILE_SIZE_MB = 20
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024  # 20MB in bytes

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict" if USE_HTTPS else "Lax",
    SESSION_COOKIE_SECURE=USE_HTTPS,  # Only send cookie over HTTPS
    PERMANENT_SESSION_LIFETIME=3600,  # 1 hour session timeout
)
csrf = CSRFProtect(app)

# Configure rate limiting with Redis or in-memory storage
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",  # Use in-memory storage (upgrade to Redis for production)
)

PASSWORD_HASH = _load_password_hash()
ENABLE_2FA, TOTP_SECRET = _load_2fa_config()


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
@limiter.limit("5 per minute", methods=["POST"])  # Strict rate limit on login attempts
def login():
    if request.method == "POST":
        password = request.form.get("password", "")

        # Step 1: Verify password
        if not _verify_password(password):
            logger.warning("Failed admin login attempt (wrong password) from %s", get_remote_address())
            flash("Неверный пароль", "error")
            return render_template("login.html", enable_2fa=ENABLE_2FA)

        # Step 2: If 2FA is enabled, verify TOTP code
        if ENABLE_2FA and TOTP_SECRET:
            totp_code = request.form.get("totp_code", "").strip()

            if not totp_code:
                # Password correct but TOTP code missing
                session["password_verified"] = True
                session.permanent = False
                flash("Введите код двухфакторной аутентификации", "info")
                return render_template("login.html", enable_2fa=True, password_verified=True)

            # Verify TOTP code
            totp = pyotp.TOTP(TOTP_SECRET)
            if not totp.verify(totp_code, valid_window=1):  # Allow 1 time step tolerance
                logger.warning(
                    "Failed admin login attempt (wrong 2FA code) from %s",
                    get_remote_address()
                )
                session.pop("password_verified", None)
                flash("Неверный код двухфакторной аутентификации", "error")
                return render_template("login.html", enable_2fa=True)

        # Authentication successful
        session["authenticated"] = True
        session["password_verified"] = False  # Clear temporary flag
        session.permanent = False
        logger.info("Successful admin login from %s (2FA: %s)", get_remote_address(), ENABLE_2FA)
        return redirect(url_for("index"))

    # GET request - show login form
    password_verified = session.get("password_verified", False)
    return render_template("login.html", enable_2fa=ENABLE_2FA, password_verified=password_verified)


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

    # Security: Validate MIME type
    allowed_photo_mimes = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
    allowed_video_mimes = {"video/mp4", "video/mpeg", "video/quicktime", "video/x-msvideo"}

    if media_type == "photo" and file.mimetype not in allowed_photo_mimes:
        logger.warning("Rejected photo upload with invalid MIME type: %s", file.mimetype)
        return jsonify({
            "ok": False,
            "error": f"Недопустимый формат фото. Разрешены: JPG, PNG, GIF, WebP"
        }), 400

    if media_type == "video" and file.mimetype not in allowed_video_mimes:
        logger.warning("Rejected video upload with invalid MIME type: %s", file.mimetype)
        return jsonify({
            "ok": False,
            "error": f"Недопустимый формат видео. Разрешены: MP4, MPEG, MOV, AVI"
        }), 400

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


# ==================== МОДУЛЬ 9: Управление изображениями фигур ====================


@app.route("/body_images")
@login_required
def body_images():
    """Страница управления изображениями типов фигур."""
    import asyncio
    from app.database.requests import get_all_body_type_images

    try:
        images = asyncio.run(get_all_body_type_images())
    except Exception as exc:
        logger.exception("Failed to load body type images: %s", exc)
        flash("Ошибка загрузки изображений", "error")
        images = []

    # Группируем по gender и category
    grouped_images = {
        "male": {"current": [], "target": []},
        "female": {"current": [], "target": []},
    }

    for img in images:
        if img.gender in grouped_images and img.category in grouped_images[img.gender]:
            grouped_images[img.gender][img.category].append(img)

    # Сортируем по type_number
    for gender in grouped_images:
        for category in grouped_images[gender]:
            grouped_images[gender][category].sort(key=lambda x: int(x.type_number))

    return render_template("body_images.html", grouped_images=grouped_images)


@app.route("/upload_body_image", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def upload_body_image():
    """Загрузить изображение типа фигуры через Telegram."""
    import asyncio
    from app.database.requests import save_body_type_image

    try:
        gender = request.form.get("gender", "").strip()
        category = request.form.get("category", "").strip()
        type_number = request.form.get("type_number", "").strip()

        if not all([gender, category, type_number]):
            return jsonify({"ok": False, "error": "Все поля обязательны"}), 400

        if gender not in ["male", "female"]:
            return jsonify({"ok": False, "error": "Неверный пол (male/female)"}), 400

        if category not in ["current", "target"]:
            return jsonify({"ok": False, "error": "Неверная категория (current/target)"}), 400

        if not type_number.isdigit() or not (1 <= int(type_number) <= 4):
            return jsonify({"ok": False, "error": "Номер типа должен быть от 1 до 4"}), 400

        file = request.files.get("file")
        if not file:
            return jsonify({"ok": False, "error": "Файл не загружен"}), 400

        # Отправляем фото в Telegram для получения file_id
        files = {"photo": (file.filename, file.stream, file.content_type)}
        data = {"chat_id": ADMIN_CHAT_ID}

        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        response = requests.post(telegram_url, data=data, files=files, timeout=30)

        if not response.ok:
            logger.error("Telegram upload failed: %s", response.text)
            return jsonify({"ok": False, "error": "Telegram API error"}), 500

        result = response.json()
        if not result.get("ok"):
            return jsonify({"ok": False, "error": "Telegram не принял файл"}), 500

        file_id = _extract_file_id("photo", result.get("result"))
        if not file_id:
            return jsonify({"ok": False, "error": "Не удалось получить file_id"}), 500

        # Сохраняем в БД
        caption = f"{gender.capitalize()}, {category}, Тип {type_number}"
        success = asyncio.run(
            save_body_type_image(
                gender=gender,
                category=category,
                type_number=type_number,
                file_id=file_id,
                caption=caption,
            )
        )

        if success:
            logger.info(
                "Body type image uploaded: %s/%s/%s (file_id=%s)",
                gender,
                category,
                type_number,
                file_id,
            )
            return jsonify({"ok": True, "file_id": file_id})
        else:
            return jsonify({"ok": False, "error": "Ошибка сохранения в БД"}), 500

    except Exception as exc:
        logger.exception("Body image upload error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/delete_body_image/<int:image_id>", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def delete_body_image(image_id: int):
    """Удалить изображение типа фигуры."""
    import asyncio
    from app.database.requests import delete_body_type_image

    try:
        success = asyncio.run(delete_body_type_image(image_id))
        if success:
            flash("Изображение удалено", "success")
            return jsonify({"ok": True})
        else:
            flash("Изображение не найдено", "error")
            return jsonify({"ok": False, "error": "Not found"}), 404
    except Exception as exc:
        logger.exception("Failed to delete body image %d: %s", image_id, exc)
        flash("Ошибка удаления", "error")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ==================== МОДУЛЬ 10: Настройки бота ====================


@app.route("/settings")
@login_required
def settings():
    """Страница настроек бота."""
    import asyncio
    from app.database.requests import get_all_settings
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED, DEFAULT_OFFER_TEXT

    try:
        all_settings = asyncio.run(get_all_settings())
    except Exception as exc:
        logger.exception("Failed to load settings: %s", exc)
        flash("Ошибка загрузки настроек", "error")
        all_settings = {}

    offer_text = all_settings.get(SETTING_OFFER_TEXT, DEFAULT_OFFER_TEXT)
    drip_enabled = all_settings.get(SETTING_DRIP_ENABLED, "true") == "true"

    return render_template(
        "settings.html",
        offer_text=offer_text,
        drip_enabled=drip_enabled,
    )


@app.route("/save_settings", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def save_settings():
    """Сохранить настройки бота."""
    import asyncio
    from app.database.requests import set_setting
    from app.constants import SETTING_OFFER_TEXT, SETTING_DRIP_ENABLED

    try:
        offer_text = request.form.get("offer_text", "").strip()
        drip_enabled = request.form.get("drip_enabled") == "on"

        if not offer_text:
            flash("Текст оффера не может быть пустым", "error")
            return redirect(url_for("settings"))

        # Сохраняем настройки
        asyncio.run(set_setting(SETTING_OFFER_TEXT, offer_text))
        asyncio.run(set_setting(SETTING_DRIP_ENABLED, "true" if drip_enabled else "false"))

        logger.info("Settings saved: offer_text length=%d, drip=%s", len(offer_text), drip_enabled)
        flash("✅ Настройки сохранены!", "success")
        return redirect(url_for("settings"))

    except Exception as exc:
        logger.exception("Failed to save settings: %s", exc)
        flash("Ошибка сохранения настроек", "error")
        return redirect(url_for("settings"))


@app.route("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error (HTTP 413)."""
    logger.warning("File upload rejected: size exceeds %d MB limit", MAX_FILE_SIZE_MB)
    return (
        jsonify({
            "ok": False,
            "error": f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        }),
        413
    )


@app.after_request
def set_security_headers(response):
    """Add comprehensive security headers to all responses."""
    # HSTS - Force HTTPS for 1 year (only if HTTPS is enabled)
    if USE_HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy - Restrict resource loading
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # unsafe-inline needed for inline scripts
        "style-src 'self' 'unsafe-inline'; "  # unsafe-inline needed for inline styles
        "img-src 'self' https://api.telegram.org data:; "
        "frame-ancestors 'none';"
    )

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy - Disable unnecessary features
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

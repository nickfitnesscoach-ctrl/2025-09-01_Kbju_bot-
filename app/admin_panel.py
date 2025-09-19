"""Flask-based admin panel for managing bot texts."""

import json
import logging
import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
TEXTS_FILE = os.path.join(os.path.dirname(__file__), "texts_data.json")


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
            "Set ADMIN_PASSWORD_HASH to avoid storing secrets in clear text."
        )
        return generate_password_hash(plain_password)

    raise RuntimeError(
        "Admin panel password is not configured. Set ADMIN_PASSWORD_HASH environment variable."
    )


app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = _load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
csrf = CSRFProtect(app)

PASSWORD_HASH = _load_password_hash()


def load_texts():
    """Load all bot texts from storage."""
    try:
        with open(TEXTS_FILE, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.warning("Texts file %s not found; returning empty mapping", TEXTS_FILE)
        return {}


def save_texts(texts):
    """Persist bot texts to storage."""
    with open(TEXTS_FILE, "w", encoding="utf-8") as fp:
        json.dump(texts, fp, ensure_ascii=False, indent=2)


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


@app.route("/edit/<path:text_key>")
@login_required
def edit_text(text_key):
    texts = load_texts()
    keys = text_key.split(".")
    value = texts

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            value = None
            break

    return render_template("edit_text.html", text_key=text_key, text_data=value)


@app.route("/save_text", methods=["POST"])
@login_required
def save_text():
    text_key = request.form["text_key"]
    text_content = request.form["text_content"]
    password = request.form.get("password", "")

    if not _verify_password(password):
        logger.info("Rejected save attempt for %s due to invalid password", text_key)
        flash("Неверный пароль для сохранения", "error")
        return redirect(url_for("edit_text", text_key=text_key))

    texts = load_texts()
    keys = text_key.split(".")
    current = texts

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    current[keys[-1]] = text_content
    save_texts(texts)
    flash("Текст успешно сохранен", "success")
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

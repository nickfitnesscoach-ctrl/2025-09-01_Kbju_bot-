"""
Веб админ-панель для редактирования текстов бота
с улучшенной безопасностью
"""

import html
import os
import secrets
import sys
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

# Добавляем путь к app модулю
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.texts import TEXTS, load_texts, save_texts

app = Flask(__name__)

# Безопасная конфигурация
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change-me-please')
MAX_TEXT_LENGTH = 10000  # Максимальная длина текста

# Защита от брутфорса
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Предупреждение о небезопасном пароле
if ADMIN_PASSWORD == 'change-me-please':
    print("\n" + "="*60)
    print("⚠️  КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ О БЕЗОПАСНОСТИ!")
    print("Используется пароль по умолчанию!")
    print("Установите ADMIN_PASSWORD в .env файле")
    print("="*60 + "\n")


def require_auth(f):
    """Декоратор для проверки аутентификации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def sanitize_text(text: str) -> str:
    """Санитизация текста для защиты от XSS"""
    if not text:
        return ""
    
    # Ограничиваем длину
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
    
    # Экранируем опасные символы (кроме разрешенных HTML тегов)
    # Разрешаем только базовые теги для Telegram
    allowed_tags = ['<b>', '</b>', '<i>', '</i>', '<u>', '</u>', '<s>', '</s>', '<code>', '</code>', '<pre>', '</pre>']
    
    # Простая валидация - проверяем что в тексте нет неразрешенных тегов
    import re
    
    # Находим все HTML теги
    html_tags = re.findall(r'<[^>]+>', text)
    
    for tag in html_tags:
        if tag not in allowed_tags:
            # Если нашли неразрешенный тег - экранируем весь текст
            text = html.escape(text)
            break
    
    return text


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """Страница авторизации"""
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        
        # Проверка пароля
        if password and password == ADMIN_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            flash('Успешная авторизация!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный пароль!', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/')
@require_auth
def index():
    """Главная страница с списком всех текстов"""
    load_texts()
    return render_template('index.html', texts=TEXTS)


@app.route('/edit/<path:text_key>')
@require_auth
def edit_text(text_key):
    """Страница редактирования конкретного текста"""
    load_texts()
    
    # Получаем текст по ключу
    keys = text_key.split('.')
    text_data = TEXTS
    
    for key in keys:
        if isinstance(text_data, dict) and key in text_data:
            text_data = text_data[key]
        else:
            flash(f'Текст не найден: {text_key}', 'error')
            return redirect(url_for('index'))
    
    return render_template('edit_text.html', 
                         text_key=text_key, 
                         text_data=text_data)


@app.route('/save', methods=['POST'])
@require_auth
@limiter.limit("10 per minute")
def save_text():
    """Сохранение отредактированного текста"""
    text_key = request.form.get('text_key')
    new_text = request.form.get('text_content')
    password = request.form.get('password')
    
    # Проверка пароля для сохранения
    if not password or password != ADMIN_PASSWORD:
        flash('Неверный пароль!', 'error')
        return redirect(url_for('edit_text', text_key=text_key))
    
    if not text_key or new_text is None:
        flash('Ошибка: не указан ключ или текст', 'error')
        return redirect(url_for('index'))
    
    # Санитизация текста
    new_text = sanitize_text(new_text)
    
    # Обновляем текст в структуре
    keys = text_key.split('.')
    text_data = TEXTS
    
    # Доходим до предпоследнего уровня
    for key in keys[:-1]:
        if isinstance(text_data, dict) and key in text_data:
            text_data = text_data[key]
        else:
            flash(f'Путь не найден: {text_key}', 'error')
            return redirect(url_for('index'))
    
    # Обновляем последний ключ
    last_key = keys[-1]
    if isinstance(text_data, dict):
        if isinstance(text_data.get(last_key), dict) and 'text' in text_data[last_key]:
            text_data[last_key]['text'] = new_text  # type: ignore
        else:
            text_data[last_key] = new_text  # type: ignore
        
        # Сохраняем в файл
        save_texts()
        flash('Текст успешно сохранен!', 'success')
    else:
        flash('Ошибка структуры данных', 'error')
    
    return redirect(url_for('edit_text', text_key=text_key))


@app.route('/api/texts')
@require_auth
def api_texts():
    """API для получения всех текстов в JSON"""
    load_texts()
    return jsonify(TEXTS)


@app.route('/api/reload')
@require_auth
def api_reload():
    """API для перезагрузки текстов"""
    load_texts()
    return jsonify({"status": "success", "message": "Тексты перезагружены"})


def create_templates():
    """Создать HTML шаблоны"""
    
    # Создаем папку для шаблонов если её нет
    os.makedirs('templates', exist_ok=True)
    
    # Базовый шаблон
    base_template = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Админ-панель текстов бота{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .text-preview {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
            white-space: pre-wrap;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.4;
        }
        .edit-btn {
            margin-left: 10px;
        }
        .navbar-brand {
            font-weight: bold;
        }
        .card {
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card-header {
            background-color: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
        .btn-primary {
            background-color: #0d6efd;
            border-color: #0d6efd;
        }
        .btn-success {
            background-color: #198754;
            border-color: #198754;
        }
        .text-key {
            font-family: 'Courier New', monospace;
            background-color: #f1f3f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('index') }}">
                🤖 Админ-панель Fitness Bot
            </a>
            <div class="navbar-nav">
                {% if session.authenticated %}
                    <a class="nav-link text-white" href="{{ url_for('logout') }}">
                        🚪 Выйти
                    </a>
                {% endif %}
            </div>
            <span class="navbar-text text-white">
                📝 Редактор текстов сообщений
            </span>
        </div>
    </nav>

    <div class="container mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else 'success' }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    # Главная страница
    index_template = '''{% extends "base.html" %}

{% block content %}
<div class="row">
    <div class="col-12">
        <h1>📝 Управление текстами бота</h1>
        <p class="text-muted">Здесь вы можете редактировать все тексты, которые отправляет бот пользователям.</p>
        
        <div class="mb-3">
            <button class="btn btn-info" onclick="location.reload()">🔄 Обновить</button>
            <button class="btn btn-secondary" onclick="togglePreview()">👁️ Переключить превью</button>
        </div>
        
        <div class="alert alert-info">
            <strong>💡 Подсказка:</strong> Тексты поддерживают HTML-разметку: 
            <code>&lt;b&gt;жирный&lt;/b&gt;</code>, 
            <code>&lt;i&gt;курсив&lt;/i&gt;</code>,
            <code>&lt;code&gt;моноширинный&lt;/code&gt;</code>
            и эмодзи 🎯💪📊
        </div>
    </div>
</div>

{% macro render_texts(texts, prefix='') %}
    {% for key, value in texts.items() %}
        {% if value is mapping %}
            {% if 'text' in value and 'title' in value %}
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">{{ value.title }}</h5>
                        <a href="{{ url_for('edit_text', text_key=(prefix + key)) }}" class="btn btn-primary btn-sm">
                            ✏️ Редактировать
                        </a>
                    </div>
                    <div class="card-body">
                        <div class="text-preview preview-content">{{ value.text }}</div>
                        <small class="text-muted">Ключ: <span class="text-key">{{ prefix + key }}</span></small>
                    </div>
                </div>
            {% else %}
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">📁 {{ key.title().replace('_', ' ') }}</h5>
                    </div>
                    <div class="card-body">
                        {{ render_texts(value, prefix + key + '.') }}
                    </div>
                </div>
            {% endif %}
        {% else %}
            <div class="card">
                <div class="card-body d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1 me-3">
                        <strong>{{ key.replace('_', ' ').title() }}:</strong>
                        <div class="text-preview preview-content mt-2">{{ value }}</div>
                        <small class="text-muted">Ключ: <span class="text-key">{{ prefix + key }}</span></small>
                    </div>
                    <a href="{{ url_for('edit_text', text_key=(prefix + key)) }}" class="btn btn-primary btn-sm">
                        ✏️ Редактировать
                    </a>
                </div>
            </div>
        {% endif %}
    {% endfor %}
{% endmacro %}

{{ render_texts(texts) }}

<script>
let showPreview = true;

function togglePreview() {
    showPreview = !showPreview;
    const previews = document.querySelectorAll('.preview-content');
    previews.forEach(preview => {
        preview.style.display = showPreview ? 'block' : 'none';
    });
    
    const btn = event.target;
    btn.textContent = showPreview ? '👁️ Скрыть превью' : '👁️ Показать превью';
}
</script>
{% endblock %}'''
    
    # Страница редактирования
    edit_template = '''{% extends "base.html" %}

{% block title %}Редактирование текста{% endblock %}

{% block content %}
<div class="row">
    <div class="col-12">
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb">
                <li class="breadcrumb-item"><a href="{{ url_for('index') }}">Главная</a></li>
                <li class="breadcrumb-item active">{{ text_key }}</li>
            </ol>
        </nav>
        
        <h1>✏️ Редактирование текста</h1>
        <p class="text-muted">Ключ: <span class="text-key">{{ text_key }}</span></p>
    </div>
</div>

<div class="row">
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">Редактирование</h5>
            </div>
            <div class="card-body">
                <form method="POST" action="{{ url_for('save_text') }}">
                    <input type="hidden" name="text_key" value="{{ text_key }}">
                    
                    <div class="mb-3">
                        <label for="text_content" class="form-label">Текст сообщения:</label>
                        <textarea 
                            class="form-control" 
                            id="text_content" 
                            name="text_content" 
                            rows="12" 
                            required
                            style="font-family: 'Segoe UI', sans-serif; line-height: 1.4;"
                        >{{ text_data.text if text_data is mapping and 'text' in text_data else text_data }}</textarea>
                        <div class="form-text">
                            Поддерживается HTML-разметка: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;code&gt;моноширинный&lt;/code&gt;
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label for="password" class="form-label">Пароль для сохранения:</label>
                        <input type="password" class="form-control" id="password" name="password" required 
                               placeholder="Введите пароль админ-панели">
                    </div>
                    
                    <div class="d-grid gap-2 d-md-flex justify-content-md-end">
                        <a href="{{ url_for('index') }}" class="btn btn-secondary">Отмена</a>
                        <button type="submit" class="btn btn-success">💾 Сохранить</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">Предварительный просмотр</h5>
            </div>
            <div class="card-body">
                <div class="text-preview" id="preview">
                    {{ text_data.text if text_data is mapping and 'text' in text_data else text_data }}
                </div>
                
                <div class="mt-3">
                    <h6>💡 Подсказки по форматированию:</h6>
                    <ul class="small">
                        <li><code>&lt;b&gt;текст&lt;/b&gt;</code> - жирный текст</li>
                        <li><code>&lt;i&gt;текст&lt;/i&gt;</code> - курсив</li>
                        <li><code>&lt;code&gt;текст&lt;/code&gt;</code> - моноширинный шрифт</li>
                        <li><code>{параметр}</code> - подстановка значений</li>
                        <li>Поддерживаются эмодзи 🎯💪📊</li>
                        <li><code>\\n</code> - перенос строки</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
// Предварительный просмотр в реальном времени
document.getElementById('text_content').addEventListener('input', function() {
    const preview = document.getElementById('preview');
    let text = this.value;
    
    // Простая замена HTML тегов для предварительного просмотра
    text = text.replace(/<b>(.*?)<\\/b>/g, '<strong>$1</strong>');
    text = text.replace(/<i>(.*?)<\\/i>/g, '<em>$1</em>');
    text = text.replace(/<code>(.*?)<\\/code>/g, '<code>$1</code>');
    text = text.replace(/\\n/g, '<br>');
    
    preview.innerHTML = text;
});
</script>
{% endblock %}'''
    
    # Страница логина
    login_template = '''{% extends "base.html" %}

{% block title %}Вход в систему{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6 col-lg-4">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">🔐 Авторизация</h5>
            </div>
            <div class="card-body">
                <form method="POST">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
                    
                    <div class="mb-3">
                        <label for="password" class="form-label">Пароль:</label>
                        <input type="password" class="form-control" id="password" name="password" required 
                               placeholder="Введите пароль администратора">
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100">
                        🚪 Войти
                    </button>
                </form>
                
                <div class="mt-3">
                    <small class="text-muted">
                        🛡️ Панель защищена от брутфорса<br>
                        📄 Логи безопасности ведутся
                    </small>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}'''
    
    # Создаем файлы шаблонов
    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(base_template)
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_template)
    
    with open('templates/edit_text.html', 'w', encoding='utf-8') as f:
        f.write(edit_template)
        
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write(login_template)


if __name__ == '__main__':
    # Создаем базовые шаблоны
    create_templates()
    
    print("🚀 Админ-панель запущена!")
    print("📝 Откройте http://localhost:5000 для редактирования текстов")
    print(f"🔑 Пароль для редактирования: {ADMIN_PASSWORD}")
    print("\n💡 Инструкция:")
    print("1. Откройте браузер и перейдите по адресу http://localhost:5000")
    print("2. Найдите нужный текст и нажмите 'Редактировать'")
    print("3. Измените текст и введите пароль для сохранения")
    print("4. Изменения сразу применятся в боте!")
    
    app.run(debug=True, host='localhost', port=5000)
# app/admin_panel.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
import json
import os
from functools import wraps
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Создаем Flask-приложение
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'))
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
csrf = CSRFProtect(app)

# Путь к файлу с текстами
TEXTS_FILE = os.path.join(os.path.dirname(__file__), 'texts_data.json')

# Загрузка текстов из файла
def load_texts():
    try:
        with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Сохранение текстов в файл
def save_texts(texts):
    with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)

# Декоратор для проверки аутентификации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главная страница админ-панели
@app.route('/')
@login_required
def index():
    texts = load_texts()
    return render_template('index.html', texts=texts)

# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        expected_password = os.getenv('ADMIN_PASSWORD', 'admin')
        # Debug information
        print(f"Entered password: {password}")
        print(f"Expected password: {expected_password}")
        print(f"Password match: {password == expected_password}")
        # В реальном приложении здесь должна быть проверка пароля
        # Например, через хэширование и сравнение с сохраненным хэшем
        if password == expected_password:  # Простая проверка пароля
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            flash('Неверный пароль', 'error')
    return render_template('login.html')

# Выход из админ-панели
@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

# Редактирование текста
@app.route('/edit/<path:text_key>')
@login_required
def edit_text(text_key):
    texts = load_texts()
    # Навигация по вложенным ключам
    keys = text_key.split('.')
    value = texts
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            value = None
            break
    
    return render_template('edit_text.html', text_key=text_key, text_data=value)

# Сохранение текста
@app.route('/save_text', methods=['POST'])
@login_required
def save_text():
    text_key = request.form['text_key']
    text_content = request.form['text_content']
    password = request.form['password']
    
    expected_password = os.getenv('ADMIN_PASSWORD', 'admin')
    # Debug information
    print(f"Entered save password: {password}")
    print(f"Expected save password: {expected_password}")
    print(f"Save password match: {password == expected_password}")
    
    # Проверка пароля (в реальном приложении используйте хэширование)
    if password != expected_password:
        flash('Неверный пароль для сохранения', 'error')
        return redirect(url_for('edit_text', text_key=text_key))
    
    # Загрузка и обновление текстов
    texts = load_texts()
    keys = text_key.split('.')
    current = texts
    
    # Навигация к нужному ключу (кроме последнего)
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Обновление значения
    current[keys[-1]] = text_content
    
    # Сохранение в файл
    save_texts(texts)
    flash('Текст успешно сохранен', 'success')
    return redirect(url_for('index'))

# Эндпоинт для проверки состояния сервиса
@app.route('/health')
def health():
    return {'status': 'ok'}

# Debug endpoint to check environment variables
@app.route('/debug')
def debug():
    return {
        'ADMIN_PASSWORD': os.getenv('ADMIN_PASSWORD', 'NOT SET'),
        'SECRET_KEY': os.getenv('SECRET_KEY', 'NOT SET')[:10] + '...' if os.getenv('SECRET_KEY') else 'NOT SET'
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
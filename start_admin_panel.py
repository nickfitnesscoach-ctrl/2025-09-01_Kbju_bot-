#!/usr/bin/env python3
"""
Скрипт для запуска админ-панели из корневой директории проекта
"""

import os
import sys
import subprocess

def main():
    # Получаем путь к директории app
    project_root = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(project_root, 'app')
    
    # Проверяем наличие файла admin_panel.py
    admin_panel_path = os.path.join(app_dir, 'admin_panel.py')
    if not os.path.exists(admin_panel_path):
        print(f"Ошибка: Файл {admin_panel_path} не найден")
        sys.exit(1)
    
    # Меняем текущую директорию на app
    os.chdir(app_dir)
    
    # Запускаем админ-панель
    print("Запуск админ-панели...")
    print("Админ-панель будет доступна по адресу: http://localhost:8080")
    print("Для остановки нажмите Ctrl+C")
    
    try:
        subprocess.run([sys.executable, 'admin_panel.py'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при запуске админ-панели: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nАдмин-панель остановлена")

if __name__ == '__main__':
    main()
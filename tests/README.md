# Security Tests

Тесты безопасности для проверки исправлений из security audit.

## Запуск тестов

### Из корневой папки проекта (рекомендуется)
```bash
python tests/test_rate_limiting.py
python tests/test_security_headers.py
python tests/test_webhook_security.py
```

### Из папки tests
```bash
cd tests
python test_rate_limiting.py
python test_security_headers.py
python test_webhook_security.py
```

### Запуск всех тестов сразу
```bash
# Linux/Mac
for test in tests/test_*.py; do python "$test"; done

# Windows PowerShell
Get-ChildItem tests\test_*.py | ForEach-Object { python $_.FullName }
```

## Описание тестов

### test_rate_limiting.py
Проверяет rate limiting на эндпоинте `/login`:
- Первые 5 попыток разрешены (HTTP 200)
- 6-я попытка блокируется (HTTP 429)

### test_security_headers.py
Проверяет наличие security headers:
- X-Frame-Options
- X-Content-Type-Options
- Referrer-Policy
- Permissions-Policy
- Content-Security-Policy
- Strict-Transport-Security (в HTTPS режиме)

### test_webhook_security.py
Проверяет обязательную аутентификацию webhook:
- Приложение не запускается без N8N_WEBHOOK_SECRET
- Webhook заголовки включают X-Webhook-Secret
- Конфигурация fails fast при неверных настройках

## Результаты

Все тесты должны показывать `[PASS]`:
- ✅ Rate limiting работает корректно
- ✅ Security headers настроены правильно
- ✅ Webhook аутентификация обязательна

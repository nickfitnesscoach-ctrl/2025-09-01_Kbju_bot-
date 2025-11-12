# Two-Factor Authentication (2FA) Setup

## Описание

Двухфакторная аутентификация (2FA) значительно повышает безопасность админ-панели, требуя не только пароль, но и временный код из приложения-аутентификатора.

## Зачем нужен 2FA?

- **Защита от взлома паролей**: Даже если пароль украден, злоумышленник не сможет войти без второго фактора
- **Защита от фишинга**: Временные коды меняются каждые 30 секунд
- **Соответствие стандартам безопасности**: Многие стандарты (PCI-DSS, SOC 2) требуют 2FA для административных панелей
- **Защита от brute-force**: Даже с rate limiting, 2FA добавляет дополнительный уровень защиты

## Шаг 1: Установка приложения-аутентификатора

Установите одно из приложений на ваш смартфон:

- **Google Authenticator** (iOS, Android)
- **Microsoft Authenticator** (iOS, Android)
- **Authy** (iOS, Android, Desktop) - рекомендуется для резервного копирования
- **1Password** (если используете менеджер паролей)

## Шаг 2: Генерация TOTP Secret

Выполните следующую команду для генерации секретного ключа:

```bash
python -c "import pyotp; print(pyotp.random_base32())"
```

Пример вывода:
```
JBSWY3DPEHPK3PXP
```

**ВАЖНО**: Сохраните этот ключ в надёжном месте! Если вы его потеряете, придётся сбрасывать 2FA.

## Шаг 3: Настройка в .env

Добавьте в ваш `.env` файл:

```bash
# Enable Two-Factor Authentication
ENABLE_2FA=True
TOTP_SECRET=JBSWY3DPEHPK3PXP  # Замените на сгенерированный ключ
```

## Шаг 4: Генерация QR-кода

Используйте готовый скрипт из папки `utils/`:

```bash
python utils/generate_2fa_qr.py
```

Этот скрипт автоматически:
- Читает `TOTP_SECRET` из `.env`
- Генерирует QR-код
- Сохраняет файл `2fa_qr_code.png`
- Показывает текущий TOTP код для тестирования

## Шаг 5: Сканирование QR-кода

1. Откройте файл `2fa_qr_code.png`
2. В приложении-аутентификаторе выберите "Добавить аккаунт" или "Scan QR Code"
3. Отсканируйте QR-код
4. Приложение начнёт генерировать 6-значные коды каждые 30 секунд

## Шаг 6: Первый вход с 2FA

1. Перезапустите админ-панель:
```bash
sudo systemctl restart admin-panel
```

2. Откройте админ-панель в браузере
3. Введите пароль
4. Введите 6-значный код из приложения-аутентификатора
5. Нажмите "Войти"

## Восстановление доступа

### Если потеряли телефон

1. Временно отключите 2FA в `.env`:
```bash
ENABLE_2FA=False
```

2. Перезапустите приложение
3. Войдите с паролем
4. Сгенерируйте новый TOTP_SECRET
5. Включите 2FA снова

### Если потеряли TOTP_SECRET

1. Сгенерируйте новый ключ:
```bash
python -c "import pyotp; print(pyotp.random_base32())"
```

2. Обновите `.env` файл
3. Перезапустите приложение
4. Создайте новый QR-код и добавьте в аутентификатор

## Резервное копирование

### Метод 1: Сохранение TOTP_SECRET

Храните `TOTP_SECRET` в безопасном месте:
- Менеджер паролей (1Password, Bitwarden)
- Зашифрованное хранилище
- Физический сейф

### Метод 2: Использование Authy

Authy позволяет синхронизировать токены между устройствами и создавать резервные копии.

### Метод 3: Множественные устройства

Отсканируйте один и тот же QR-код на нескольких устройствах (телефон + планшет).

## Отключение 2FA

Если вам нужно отключить 2FA:

```bash
# В .env файле
ENABLE_2FA=False
```

Перезапустите приложение. После этого будет требоваться только пароль.

## Тестирование 2FA

Создайте тестовый скрипт `test_2fa.py`:

```python
import os
import pyotp
from dotenv import load_dotenv

load_dotenv()

TOTP_SECRET = os.getenv("TOTP_SECRET")
if not TOTP_SECRET:
    print("Error: TOTP_SECRET not found")
    exit(1)

totp = pyotp.TOTP(TOTP_SECRET)
current_code = totp.now()

print(f"Current TOTP code: {current_code}")
print(f"This code is valid for the next {30 - (int(time.time()) % 30)} seconds")

# Verify the code
is_valid = totp.verify(current_code)
print(f"Code verification: {'VALID' if is_valid else 'INVALID'}")
```

## Безопасность

### Рекомендации

1. **Никогда не делитесь TOTP_SECRET**: Этот ключ даёт полный доступ к генерации кодов
2. **Используйте резервное копирование**: Сохраните TOTP_SECRET в безопасном месте
3. **Регулярно проверяйте**: Убедитесь, что приложение работает корректно
4. **Используйте с HTTPS**: 2FA максимально эффективен только с HTTPS

### Что защищает 2FA

✅ Защита от украденных паролей
✅ Защита от фишинга
✅ Защита от replay атак
✅ Соответствие стандартам безопасности

### Что НЕ защищает 2FA

❌ Не защищает от keyloggers (если злоумышленник на вашем компьютере)
❌ Не защищает от session hijacking (используйте HTTPS!)
❌ Не защищает от social engineering

## Troubleshooting

### Коды не принимаются

**Проблема**: Введённый код всегда неверный

**Решения**:
1. Проверьте синхронизацию времени на сервере:
```bash
timedatectl status
```

2. Синхронизируйте время:
```bash
sudo timedatectl set-ntp true
```

3. Проверьте часовой пояс:
```bash
sudo timedatectl set-timezone UTC
```

### Приложение не генерирует коды

**Проблема**: После сканирования QR-кода коды не появляются

**Решения**:
1. Убедитесь, что QR-код отсканирован правильно
2. Попробуйте ввести TOTP_SECRET вручную
3. Проверьте, что приложение-аутентификатор установлено корректно

### Слишком часто блокировка

**Проблема**: Rate limiting блокирует даже при правильном вводе

**Решение**: Увеличьте лимит в `admin_panel.py`:
```python
@limiter.limit("10 per minute", methods=["POST"])  # Было "5 per minute"
```

## Дополнительные ресурсы

- [TOTP RFC 6238](https://tools.ietf.org/html/rfc6238)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [pyotp Documentation](https://pyauth.github.io/pyotp/)

## Пример полной настройки

```bash
# 1. Генерация ключа
python -c "import pyotp; print(pyotp.random_base32())"
# Output: JBSWY3DPEHPK3PXP

# 2. Добавление в .env
echo "ENABLE_2FA=True" >> .env
echo "TOTP_SECRET=JBSWY3DPEHPK3PXP" >> .env

# 3. Генерация QR-кода
python utils/generate_2fa_qr.py

# 4. Перезапуск приложения
sudo systemctl restart admin-panel
```

После этого откройте админ-панель и войдите с паролем + 2FA кодом!

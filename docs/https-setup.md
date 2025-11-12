# HTTPS Setup для Admin Panel

## Описание

Для защиты админ-панели от атак перехвата данных необходимо настроить HTTPS. Этот документ описывает процесс настройки с использованием nginx в качестве reverse proxy.

## Зачем нужен HTTPS?

- **Защита паролей**: Без HTTPS пароли передаются в открытом виде
- **Защита session cookies**: Предотвращает кражу сессий
- **Защита от MITM атак**: Шифрует весь трафик между браузером и сервером
- **HSTS**: Браузер будет автоматически использовать только HTTPS

## Настройка с nginx + Let's Encrypt

### 1. Установка nginx и certbot

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install nginx certbot python3-certbot-nginx
```

### 2. Конфигурация nginx

Создайте файл `/etc/nginx/sites-available/admin-panel`:

```nginx
# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name your-domain.com;

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates (will be configured by certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers (additional to Flask headers)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Proxy to Flask application
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Increase timeouts for media uploads
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 3. Получение SSL сертификата

```bash
# Создайте символическую ссылку
sudo ln -s /etc/nginx/sites-available/admin-panel /etc/nginx/sites-enabled/

# Проверьте конфигурацию nginx
sudo nginx -t

# Получите сертификат от Let's Encrypt
sudo certbot --nginx -d your-domain.com

# Перезапустите nginx
sudo systemctl restart nginx
```

### 4. Настройка автообновления сертификата

```bash
# Certbot автоматически добавляет задачу в cron
# Проверьте, что обновление работает
sudo certbot renew --dry-run
```

### 5. Включение HTTPS в приложении

Добавьте в `.env`:

```bash
USE_HTTPS=True
```

Перезапустите приложение:

```bash
sudo systemctl restart admin-panel  # или ваша команда запуска
```

## Альтернатива: Локальная разработка с самоподписанным сертификатом

Для локальной разработки можно использовать самоподписанный сертификат:

```bash
# Создайте самоподписанный сертификат
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/CN=localhost"

# Запустите Flask с SSL
# В admin_panel.py измените:
if __name__ == "__main__":
    import ssl
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('cert.pem', 'key.pem')
    app.run(host="0.0.0.0", port=8080, debug=False, ssl_context=context)
```

**Внимание**: Браузеры будут показывать предупреждение о недоверенном сертификате. Это нормально для локальной разработки.

## Проверка настройки

1. Откройте https://your-domain.com в браузере
2. Проверьте, что:
   - Соединение защищено (замок в адресной строке)
   - HTTP автоматически перенаправляет на HTTPS
   - Session cookie имеет флаг `Secure`

3. Проверьте security headers:
```bash
curl -I https://your-domain.com/health
```

Должны присутствовать:
- `Strict-Transport-Security`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Content-Security-Policy`

## Рекомендации для production

1. **Используйте firewall**: Закройте прямой доступ к порту 8080
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8080/tcp
```

2. **Запускайте Flask через systemd**: Не используйте встроенный Flask сервер
```bash
# Используйте gunicorn или uWSGI
gunicorn -w 4 -b 127.0.0.1:8080 app.admin_panel:app
```

3. **Мониторинг сертификатов**: Настройте оповещения об истечении SSL сертификата

4. **Регулярные обновления**: Следите за обновлениями nginx и certbot

## Безопасность после настройки HTTPS

После включения HTTPS приложение автоматически:
- ✅ Устанавливает `SESSION_COOKIE_SECURE=True` (только HTTPS)
- ✅ Устанавливает `SESSION_COOKIE_SAMESITE="Strict"`
- ✅ Добавляет HSTS header (браузер запомнит использовать только HTTPS)
- ✅ Защищает от перехвата session cookies
- ✅ Защищает пароли при передаче

## Troubleshooting

### Ошибка "Too many redirects"
- Проверьте, что Flask знает о HTTPS: установите `X-Forwarded-Proto` в nginx
- Убедитесь, что `USE_HTTPS=True` в `.env`

### Session cookie не работает
- Проверьте, что домен совпадает
- Убедитесь, что браузер не блокирует cookies
- Проверьте флаги cookie в DevTools

### Certbot не может получить сертификат
- Убедитесь, что порт 80 открыт
- Проверьте DNS записи домена
- Убедитесь, что nginx запущен

## Дополнительные ресурсы

- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [OWASP Transport Layer Protection](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/09-Testing_for_Weak_Cryptography/01-Testing_for_Weak_Transport_Layer_Security)

"""
Константы для Fitness Bot
Централизованное хранение всех констант приложения
"""

# Rate limiting
USER_REQUESTS_LIMIT = 30
USER_REQUESTS_WINDOW = 60  # seconds

# Таймеры
DEFAULT_CALCULATED_TIMER_DELAY = 60  # minutes
DELAYED_OFFER_DELAY = 3  # seconds

# Админ-лист лидов
LEADS_PAGE_SIZE = 10
LEADS_DEFAULT_WINDOW = "all"

# Валидация пользовательских данных
VALIDATION_LIMITS = {
    'age': {'min': 15, 'max': 80},
    'weight': {'min': 30, 'max': 200},
    'height': {'min': 140, 'max': 220}
}

# Безопасность
MAX_TEXT_LENGTH = 100
DB_OPERATION_TIMEOUT = 10.0  # seconds
# Количество повторов при временных ошибках БД (например, database is locked)
DB_OPERATION_RETRIES = 3
# Базовая пауза между повторами (будет увеличиваться линейно)
DB_OPERATION_RETRY_DELAY = 0.5  # seconds

# Статусы воронки лидов
FUNNEL_STATUSES = {
    'new': 'new',
    'calculated': 'calculated',
    'hotlead_consultation': 'hotlead_consultation',
}

FUNNEL_STATUS_LABELS = {
    FUNNEL_STATUSES['new']: 'Новый лид',
    FUNNEL_STATUSES['calculated']: 'Получил расчёт',
    FUNNEL_STATUSES['hotlead_consultation']: 'Записан на диагностику',
}

# Часовые пояса России + Европа
TIMEZONES = {
    "msk": "🏛 Москва (МСК, UTC+3)",
    "spb": "🏰 Санкт-Петербург (МСК, UTC+3)",
    "kazan": "🕌 Казань (МСК, UTC+3)",
    "ufa": "🏔 Уфа (МСК, UTC+3)",
    "tyumen": "🌲 Тюмень (GMT+5)",
    "yekt": "🏭 Екатеринбург (GMT+5)",
    "nsk": "🌆 Новосибирск (GMT+7)",
    "kras": "🏞 Красноярск (GMT+7)",
    "irk": "🏔 Иркутск (GMT+8)",
    "vlad": "🌊 Владивосток (GMT+10)",
    "cet": "🇪🇺 Центральная Европа (CET, UTC+1)",
    "eet": "🇪🇺 Восточная Европа (EET, UTC+2)",
}

# Настройки бота (ключи для bot_settings)
SETTING_OFFER_TEXT = "offer_text"
SETTING_DRIP_ENABLED = "drip_enabled"

# Дефолтный текст оффера
DEFAULT_OFFER_TEXT = """
💪 Хочешь получить персональный план питания и тренировок?

📲 Напиши тренеру для консультации!
"""

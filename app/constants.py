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

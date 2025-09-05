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

# Приоритеты лидов
PRIORITY_SCORES = {
    'consultation_request': 100,  # Максимальный приоритет для заявок на консультацию
    'hotlead_delayed': 80,        # Высокий приоритет для отложенных горячих лидов
    'coldlead_delayed': 10,       # Низкий приоритет для холодных лидов
    'coldlead': 5,                # Минимальный приоритет для обычных холодных лидов
    'new': 0                      # Базовый приоритет для новых пользователей
}

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
    'hotlead_delayed': 'hotlead_delayed',
    'coldlead_delayed': 'coldlead_delayed',
    'coldlead': 'coldlead'
}

# Приоритеты пользователей
USER_PRIORITIES = {
    'nutrition': 'nutrition',
    'training': 'training', 
    'schedule': 'schedule'
}

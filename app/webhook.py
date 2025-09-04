"""
Webhook сервис для интеграции с n8n
Отправляет данные лидов в n8n для автоматизации
Включает retry механизм, мониторинг и валидацию
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any

import aiohttp

from config import DEBUG, N8N_WEBHOOK_URL

logger = logging.getLogger(__name__)


class WebhookMetrics:
    """Класс для отслеживания метрик webhook'ов"""
    
    success_count = 0
    error_count = 0
    last_error_time: Optional[datetime] = None
    last_error_message: Optional[str] = None
    
    @classmethod
    def log_success(cls, lead_type: Optional[str] = None):
        """Записать успешную отправку"""
        cls.success_count += 1
        if DEBUG:
            logger.info(f"[WEBHOOK] Успешно отправлен {lead_type or 'unknown'} лид")
    
    @classmethod
    def log_error(cls, error_message: str, lead_type: Optional[str] = None):
        """Записать ошибку отправки"""
        cls.error_count += 1
        cls.last_error_time = datetime.utcnow()
        cls.last_error_message = error_message
        logger.error(f"[WEBHOOK] Ошибка отправки {lead_type or 'unknown'} лида: {error_message}")
    
    @classmethod
    def get_health(cls) -> dict:
        """Получить статистику здоровья webhook'ов"""
        total_requests = cls.success_count + cls.error_count
        return {
            'total_requests': total_requests,
            'success_count': cls.success_count,
            'error_count': cls.error_count,
            'success_rate': cls.success_count / total_requests if total_requests > 0 else 0,
            'last_error_time': cls.last_error_time.isoformat() if cls.last_error_time else None,
            'last_error_message': cls.last_error_message,
            'status': 'healthy' if (cls.success_count / total_requests if total_requests > 0 else 1) > 0.8 else 'degraded'
        }



def validate_payload(payload: dict, lead_type: str) -> bool:
    """
    Валидация payload перед отправкой
    
    Args:
        payload: данные для отправки
        lead_type: тип лида
        
    Returns:
        bool: True если payload валиден
    
    Raises:
        ValueError: при отсутствии обязательных полей
    """
    # Обязательные поля для всех типов лидов
    required_fields = ['user_id', 'lead_type', 'timestamp']
    
    # Проверяем обязательные поля
    missing_fields = [field for field in required_fields if field not in payload or payload[field] is None]
    
    if missing_fields:
        raise ValueError(f"Отсутствуют обязательные поля: {missing_fields}")
    
    # Проверяем тип лида
    if payload['lead_type'] not in ['hot', 'cold', 'calculated']:
        raise ValueError(f"Некорректный тип лида: {payload['lead_type']}")
    
    # Проверяем user_id
    if not isinstance(payload['user_id'], (int, str)) or not payload['user_id']:
        raise ValueError("Некорректный user_id")
    
    # Дополнительная валидация для горячих лидов
    if lead_type == 'hot' and 'priority' not in payload:
        logger.warning("Горячий лид без приоритета")
    
    return True


async def send_with_retry(payload: dict, max_attempts: int = 3) -> bool:
    """
    Отправка с retry механизмом для критичных лидов
    
    Args:
        payload: данные для отправки
        max_attempts: максимальное количество попыток
        
    Returns:
        bool: успешность отправки
    """
    if not N8N_WEBHOOK_URL:
        if DEBUG:
            logger.info(f"[DEBUG] Webhook отключен - отправили бы {payload.get('lead_type')} лид: {payload.get('user_id')}")
        return True
    
    for attempt in range(max_attempts):
        try:
            # Валидируем payload
            validate_payload(payload, payload.get('lead_type', 'unknown'))
            
            async with aiohttp.ClientSession() as session:
                # Увеличиваем timeout для retry
                timeout = aiohttp.ClientTimeout(total=5 + attempt * 2)
                
                async with session.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    timeout=timeout,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        WebhookMetrics.log_success(payload.get('lead_type', 'unknown'))
                        if DEBUG:
                            logger.info(f"[SUCCESS] {payload.get('lead_type', 'unknown')} лид отправлен в n8n: {payload.get('user_id')} (попытка {attempt + 1})")
                        return True
                    else:
                        error_msg = f"HTTP {response.status}"
                        if DEBUG:
                            response_text = await response.text()
                            error_msg += f": {response_text}"
                        
                        # Не retry для 4xx ошибок (клиентские ошибки)
                        if 400 <= response.status < 500:
                            WebhookMetrics.log_error(error_msg, payload.get('lead_type', 'unknown'))
                            logger.error(f"[ERROR] Клиентская ошибка, retry не будет: {error_msg}")
                            return False
                        
                        if attempt == max_attempts - 1:
                            WebhookMetrics.log_error(error_msg, payload.get('lead_type', 'unknown'))
                            logger.error(f"[ERROR] Не удалось отправить после {max_attempts} попыток: {error_msg}")
                        else:
                            logger.warning(f"[RETRY] Попытка {attempt + 1} неудачна: {error_msg}")
                        
        except ValueError as e:
            # Ошибка валидации - не retry
            WebhookMetrics.log_error(str(e), payload.get('lead_type'))
            logger.error(f"[ERROR] Ошибка валидации: {e}")
            return False
            
        except asyncio.TimeoutError:
            error_msg = f"Таймаут {5 + attempt * 2}с"
            if attempt == max_attempts - 1:
                WebhookMetrics.log_error(error_msg, payload.get('lead_type'))
                logger.error(f"[ERROR] Webhook таймаут после {max_attempts} попыток: {payload.get('user_id')}")
            else:
                logger.warning(f"[RETRY] Таймаут на попытке {attempt + 1}: {payload.get('user_id')}")
                
        except Exception as e:
            error_msg = str(e)
            if attempt == max_attempts - 1:
                WebhookMetrics.log_error(error_msg, payload.get('lead_type'))
                logger.error(f"[ERROR] Webhook ошибка после {max_attempts} попыток: {e}")
            else:
                logger.warning(f"[RETRY] Ошибка на попытке {attempt + 1}: {e}")
        
        # Экспоненциальный backoff
        if attempt < max_attempts - 1:
            delay = 2 ** attempt  # 1, 2, 4 секунды
            logger.info(f"[RETRY] Ожидание {delay}с перед следующей попыткой")
            await asyncio.sleep(delay)
    
    return False


class WebhookService:
    
    @staticmethod
    async def send_lead_to_n8n(user_data: dict, lead_type: str, **extra_data) -> bool:
        """
        Отправить лид в n8n с retry механизмом
        
        Args:
            user_data: данные пользователя из БД
            lead_type: тип лида ('hot', 'cold', 'calculated')
            **extra_data: дополнительные данные
            
        Returns:
            bool: успешность отправки
        """
        # Формируем payload для n8n
        payload = {
            'lead_type': lead_type,
            'user_id': user_data.get('tg_id'),
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'gender': user_data.get('gender', ''),
            'age': user_data.get('age', 0),
            'weight': user_data.get('weight', 0.0),
            'height': user_data.get('height', 0),
            'activity': user_data.get('activity', ''),
            'goal': user_data.get('goal', ''),
            'calories': user_data.get('calories', 0),
            'proteins': user_data.get('proteins', 0),
            'fats': user_data.get('fats', 0),
            'carbs': user_data.get('carbs', 0),
            'timestamp': datetime.utcnow().isoformat(),
            **extra_data
        }
        
        # Определяем количество попыток в зависимости от типа лида
        if lead_type == 'hot':  # Критичные лиды
            max_attempts = 5
        elif lead_type == 'calculated':  # Потерянные лиды
            max_attempts = 3
        else:  # Холодные лиды
            max_attempts = 2
        
        return await send_with_retry(payload, max_attempts)
    
    
    @staticmethod  
    async def send_hot_lead(user_data: dict, priority: str):
        """Отправить горячий лид"""
        return await WebhookService.send_lead_to_n8n(
            user_data,
            'hot',
            priority=priority,
            ready_for_system=True
        )
    
    
    @staticmethod
    async def send_cold_lead(user_data: dict):
        """Отправить холодный лид"""
        return await WebhookService.send_lead_to_n8n(
            user_data,
            'cold',
            needs_advice=True
        )
    
    
    @staticmethod
    async def send_calculated_lead(user_data: dict, calculated_at: Optional[datetime] = None):
        """Отправить calculated лид (потерянный)"""
        extra_data = {}
        if calculated_at:
            extra_data['calculated_at'] = calculated_at.isoformat()
            
        return await WebhookService.send_lead_to_n8n(
            user_data,
            'calculated',
            **extra_data
        )
    
    @staticmethod
    def get_webhook_health() -> dict:
        """Получить статистику здоровья webhook'ов"""
        return WebhookMetrics.get_health()
    
    @staticmethod
    def reset_metrics():
        """Сбросить метрики (для тестирования)"""
        WebhookMetrics.success_count = 0
        WebhookMetrics.error_count = 0
        WebhookMetrics.last_error_time = None
        WebhookMetrics.last_error_message = None


# Простой сервис для системы таймеров
# TODO: Для продакшена - перенести хранение таймеров в Redis
# чтобы они не терялись при перезапуске
# Пример реализации:
# import redis
# redis_client = redis.Redis(host='localhost', port=6379, db=0)
# Хранить: redis_client.setex(f"timer:{user_id}", ttl_seconds, timer_data)
# Восстанавливать: redis_client.get(f"timer:{user_id}")
class TimerService:
    
    # Хранилище активных таймеров
    active_timers = {}
    
    @classmethod
    async def start_calculated_timer(cls, user_id: int, delay_minutes: int = 60):
        """
        Запуск таймера для отправки calculated лида
        
        Args:
            user_id: ID пользователя в Telegram
            delay_minutes: задержка в минутах (по умолчанию 60)
        """
        
        # Отменяем предыдущий таймер если есть
        cls.cancel_timer(user_id)
        
        async def timer_callback():
            await asyncio.sleep(delay_minutes * 60)  # конвертируем в секунды
            
            # Проверяем статус пользователя
            from app.database.requests import get_user
            
            try:
                user = await get_user(user_id)
                if user and user.funnel_status == 'calculated':
                    # Пользователь не продолжил воронку - отправляем как calculated лид
                    user_dict = cls._user_to_dict(user)
                    await WebhookService.send_calculated_lead(user_dict, user.calculated_at)
                    
                    if DEBUG:
                        print(f"[TIMER] Отправлен calculated лид для пользователя {user_id}")
                        
            except Exception as e:
                print(f"[TIMER ERROR] Ошибка обработки таймера для {user_id}: {e}")
            finally:
                # Удаляем таймер из активных
                cls.active_timers.pop(user_id, None)
        
        # Создаем и запускаем таймер
        task = asyncio.create_task(timer_callback())
        cls.active_timers[user_id] = task
        
        if DEBUG:
            print(f"[TIMER] Запущен таймер на {delay_minutes} мин для пользователя {user_id}")
    
    
    @classmethod
    def cancel_timer(cls, user_id: int):
        """Отменить таймер для пользователя"""
        if user_id in cls.active_timers:
            cls.active_timers[user_id].cancel()
            del cls.active_timers[user_id]
            
            if DEBUG:
                print(f"[TIMER] Отменен таймер для пользователя {user_id}")
    
    
    @staticmethod
    def _user_to_dict(user) -> dict:
        """Конвертировать объект User в словарь"""
        return {
            'tg_id': user.tg_id,
            'username': user.username,
            'first_name': user.first_name,
            'gender': user.gender,
            'age': user.age,
            'weight': user.weight,
            'height': user.height,
            'activity': user.activity,
            'goal': user.goal,
            'calories': user.calories,
            'proteins': user.proteins,
            'fats': user.fats,
            'carbs': user.carbs
        }


# Утилиты для тестирования webhook
async def test_webhook_connection() -> dict:
    """
    Тестировать соединение с webhook
    
    Returns:
        dict: детальный отчет о тестировании
    """
    if not N8N_WEBHOOK_URL:
        return {
            'status': 'disabled',
            'message': 'N8N_WEBHOOK_URL не установлен',
            'success': False,
            'response_time': None
        }
        
    test_data = {
        'test': True,
        'timestamp': datetime.utcnow().isoformat(),
        'message': 'Test connection from Fitness Bot',
        'version': '2.0',
        'user_id': 'test_user',
        'lead_type': 'test'
    }
    
    start_time = datetime.utcnow()
    
    try:
        # Используем наш retry механизм
        success = await send_with_retry(test_data, max_attempts=1)
        
        response_time = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            'status': 'success' if success else 'failed',
            'message': 'Тест прошел успешно' if success else 'Тест не прошел',
            'success': success,
            'response_time': response_time,
            'webhook_url': N8N_WEBHOOK_URL[:50] + '...' if len(N8N_WEBHOOK_URL) > 50 else N8N_WEBHOOK_URL,
            'health': WebhookMetrics.get_health()
        }
                
    except Exception as e:
        response_time = (datetime.utcnow() - start_time).total_seconds()
        return {
            'status': 'error',
            'message': f'Ошибка тестирования: {str(e)}',
            'success': False,
            'response_time': response_time,
            'error': str(e)
        }
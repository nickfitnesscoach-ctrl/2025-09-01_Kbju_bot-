"""
Webhook сервис для интеграции с n8n
Отправляет данные лидов в n8n для автоматизации
"""

import asyncio
from datetime import datetime

import aiohttp

from config import DEBUG, N8N_WEBHOOK_URL


class WebhookService:
    
    @staticmethod
    async def send_lead_to_n8n(user_data: dict, lead_type: str, **extra_data):
        """
        Отправить лид в n8n
        
        Args:
            user_data: данные пользователя из БД
            lead_type: тип лида ('hot', 'cold', 'calculated')
            **extra_data: дополнительные данные
            
        Returns:
            bool: успешность отправки
        """
        
        if not N8N_WEBHOOK_URL:
            if DEBUG:
                print(f"[DEBUG] Webhook отключен - отправили бы {lead_type} лид: {user_data.get('tg_id')}")
            return True
            
        # Формируем payload для n8n
        payload = {
            'lead_type': lead_type,
            'user_id': user_data.get('tg_id'),
            'username': user_data.get('username'),
            'first_name': user_data.get('first_name'),
            'gender': user_data.get('gender'),
            'age': user_data.get('age'),
            'weight': user_data.get('weight'),
            'height': user_data.get('height'),
            'activity': user_data.get('activity'),
            'goal': user_data.get('goal'),
            'calories': user_data.get('calories'),
            'proteins': user_data.get('proteins'),
            'fats': user_data.get('fats'),
            'carbs': user_data.get('carbs'),
            'timestamp': datetime.utcnow().isoformat(),
            **extra_data
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        if DEBUG:
                            print(f"[SUCCESS] {lead_type} лид отправлен в n8n: {user_data.get('tg_id')}")
                        return True
                    else:
                        print(f"[ERROR] n8n webhook ошибка: {response.status}")
                        if DEBUG:
                            response_text = await response.text()
                            print(f"[ERROR] Ответ сервера: {response_text}")
                        return False
                        
        except asyncio.TimeoutError:
            print(f"[ERROR] Webhook таймаут для пользователя {user_data.get('tg_id')}")
            return False
        except Exception as e:
            print(f"[ERROR] Webhook ошибка для пользователя {user_data.get('tg_id')}: {e}")
            return False
    
    
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
    async def send_calculated_lead(user_data: dict, calculated_at: datetime = None):
        """Отправить calculated лид (потерянный)"""
        extra_data = {}
        if calculated_at:
            extra_data['calculated_at'] = calculated_at.isoformat()
            
        return await WebhookService.send_lead_to_n8n(
            user_data,
            'calculated',
            **extra_data
        )


# Простой сервис для системы таймеров
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
async def test_webhook_connection():
    """Тестировать соединение с webhook"""
    if not N8N_WEBHOOK_URL:
        print("[TEST] N8N_WEBHOOK_URL не установлен")
        return False
        
    test_data = {
        'test': True,
        'timestamp': datetime.utcnow().isoformat(),
        'message': 'Test connection from Fitness Bot'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_WEBHOOK_URL,
                json=test_data,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                print(f"[TEST] Webhook ответ: {response.status}")
                return response.status == 200
                
    except Exception as e:
        print(f"[TEST] Webhook ошибка: {e}")
        return False
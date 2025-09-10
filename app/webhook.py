"""
Webhook сервис для интеграции с n8n
Отправляет данные о пользователях в Google Sheets через n8n Webhook
"""

import aiohttp
import asyncio
from datetime import datetime
import logging
from typing import Union, Dict, Any

# Import from the correct location
from app.database.models import User
from config import N8N_WEBHOOK_URL, DEBUG, N8N_WEBHOOK_SECRET

logger = logging.getLogger(__name__)


async def send_lead_to_n8n(user: User, event: str = "kbju_lead") -> bool:
    """
    Отправить данные пользователя в n8n Webhook.
    
    Args:
        user: объект User из БД
        event: название события (по умолчанию kbju_lead)
    Returns:
        bool: успешно ли отправлено
    """

    if not N8N_WEBHOOK_URL:
        if DEBUG:
            print("[Webhook] ⚠️ N8N_WEBHOOK_URL не задан — данные не отправлены")
        return False

    # Формируем payload под n8n
    payload = {
        "tg_id": user.tg_id,
        "username": user.username,
        "first_name": user.first_name,
        "gender": user.gender,
        "age": user.age,
        "weight": user.weight,
        "height": user.height,
        "activity": user.activity,
        "goal": user.goal,
        "calories": user.calories,
        "proteins": user.proteins,
        "fats": user.fats,
        "carbs": user.carbs,
        "funnel_status": user.funnel_status,
        "priority": user.priority,
        "priority_score": user.priority_score,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "calculated_at": user.calculated_at.isoformat() if user.calculated_at else None,
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Retry логика: до 3 попыток
    for attempt in range(3):
        try:
            timeout = aiohttp.ClientTimeout(total=5 + attempt * 2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Secret": N8N_WEBHOOK_SECRET
                    },
                ) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        if DEBUG:
                            print(
                                f"[Webhook] ✅ Lead {user.tg_id} отправлен в n8n "
                                f"(попытка {attempt + 1}): {text}"
                            )
                        return True
                    else:
                        print(
                            f"[Webhook] ❌ Ошибка {resp.status} при отправке "
                            f"(попытка {attempt + 1}): {text}"
                        )
        except Exception as e:
            print(f"[Webhook] 🔥 Ошибка на попытке {attempt + 1}: {e}")

        # backoff
        if attempt < 2:
            delay = 2 ** attempt  # 1с, 2с
            await asyncio.sleep(delay)

    return False


async def send_lead_dict_to_n8n(user_data: Dict[str, Any], event: str = "kbju_lead") -> bool:
    """
    Отправить данные пользователя из словаря в n8n Webhook.
    
    Args:
        user_data: словарь с данными пользователя
        event: название события (по умолчанию kbju_lead)
    Returns:
        bool: успешно ли отправлено
    """

    if not N8N_WEBHOOK_URL:
        if DEBUG:
            print("[Webhook] ⚠️ N8N_WEBHOOK_URL не задан — данные не отправлены")
        return False

    # Формируем payload под n8n
    payload = {
        "tg_id": user_data.get("tg_id", 0),
        "username": user_data.get("username", ""),
        "first_name": user_data.get("first_name", ""),
        "gender": user_data.get("gender", ""),
        "age": user_data.get("age", 0),
        "weight": user_data.get("weight", 0.0),
        "height": user_data.get("height", 0),
        "activity": user_data.get("activity", ""),
        "goal": user_data.get("goal", ""),
        "calories": user_data.get("calories", 0),
        "proteins": user_data.get("proteins", 0),
        "fats": user_data.get("fats", 0),
        "carbs": user_data.get("carbs", 0),
        "funnel_status": user_data.get("funnel_status", ""),
        "priority": user_data.get("priority", ""),
        "priority_score": user_data.get("priority_score", 0),
        "created_at": user_data.get("created_at", None),
        "updated_at": user_data.get("updated_at", None),
        "calculated_at": user_data.get("calculated_at", None),
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Retry логика: до 3 попыток
    for attempt in range(3):
        try:
            timeout = aiohttp.ClientTimeout(total=5 + attempt * 2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Secret": N8N_WEBHOOK_SECRET
                    },
                ) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        if DEBUG:
                            print(
                                f"[Webhook] ✅ Lead {payload['tg_id']} отправлен в n8n "
                                f"(попытка {attempt + 1}): {text}"
                            )
                        return True
                    else:
                        print(
                            f"[Webhook] ❌ Ошибка {resp.status} при отправке "
                            f"(попытка {attempt + 1}): {text}"
                        )
        except Exception as e:
            print(f"[Webhook] 🔥 Ошибка на попытке {attempt + 1}: {e}")

        # backoff
        if attempt < 2:
            delay = 2 ** attempt  # 1с, 2с
            await asyncio.sleep(delay)

    return False


# Утилита для проверки соединения
async def test_webhook_connection():
    test_payload = {
        "tg_id": "99999",
        "username": "test_user",
        "first_name": "Test",
        "gender": "male",
        "age": 30,
        "weight": 75,
        "height": 180,
        "activity": "moderate",
        "goal": "maintenance",
        "calories": 2000,
        "proteins": 100,
        "fats": 70,
        "carbs": 250,
        "funnel_status": "test",
        "priority": "nutrition",
        "priority_score": 50,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "calculated_at": datetime.utcnow().isoformat(),
        "event": "kbju_lead_test",
        "timestamp": datetime.utcnow().isoformat(),
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            N8N_WEBHOOK_URL, json=test_payload, headers={"Content-Type": "application/json"}
        ) as resp:
            text = await resp.text()
            print(f"[Webhook Test] {resp.status}: {text}")


class WebhookService:
    """Сервис для отправки webhook-ов в n8n"""
    
    @staticmethod
    async def send_lead_to_n8n(user: User, event: str = "kbju_lead") -> bool:
        """Отправить данные пользователя в n8n Webhook"""
        return await send_lead_to_n8n(user, event)
    
    @staticmethod
    async def send_hot_lead(user_data: dict, priority: str):
        """Отправить горячий лид"""
        # Add the priority to the funnel_status for hot leads
        user_data["funnel_status"] = f"hotlead_{priority}"
        return await send_lead_dict_to_n8n(user_data, "hot_lead")
    
    @staticmethod
    async def send_cold_lead(user_data: dict):
        """Отправить холодный лид"""
        if "funnel_status" not in user_data:
            user_data["funnel_status"] = "coldlead"
        return await send_lead_dict_to_n8n(user_data, "cold_lead")
    
    @staticmethod
    async def send_calculated_lead(user_data: dict):
        """Отправить calculated лид"""
        if "funnel_status" not in user_data:
            user_data["funnel_status"] = "calculated"
        return await send_lead_dict_to_n8n(user_data, "calculated_lead")


class TimerService:
    """Сервис для работы с таймерами"""
    
    active_timers = {}
    
    @classmethod
    async def start_calculated_timer(cls, user_id: int, delay_minutes: int = 60):
        """Запустить таймер для пользователя"""
        # Отменяем предыдущий таймер если есть
        cls.cancel_timer(user_id)
        
        async def timer_callback():
            await asyncio.sleep(delay_minutes * 60)  # конвертируем в секунды
            
            # Здесь должна быть логика обработки таймера
            # Пока просто логируем
            if DEBUG:
                print(f"[TIMER] Таймер сработал для пользователя {user_id}")
            
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
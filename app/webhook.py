"""
Webhook сервис для интеграции с n8n
Отправляет данные о пользователях в Google Sheets через n8n Webhook
"""

import aiohttp
import asyncio
from datetime import datetime
from app.models import User
from config import N8N_WEBHOOK_URL, DEBUG


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
                    headers={"Content-Type": "application/json"},
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

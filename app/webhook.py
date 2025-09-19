"""
Webhook сервис для интеграции с n8n
Отправляет данные о пользователях в Google Sheets через n8n Webhook
"""

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, Union

import aiohttp

from app.database.models import User
from config import DEBUG, N8N_WEBHOOK_SECRET, N8N_WEBHOOK_URL

logger = logging.getLogger(__name__)

_USER_FIELDS_DEFAULTS: Dict[str, Any] = {
    "tg_id": 0,
    "username": "",
    "first_name": "",
    "gender": "",
    "age": 0,
    "weight": 0.0,
    "height": 0,
    "activity": "",
    "goal": "",
    "calories": 0,
    "proteins": 0,
    "fats": 0,
    "carbs": 0,
    "funnel_status": "",
    "priority": "",
    "priority_score": 0,
    "created_at": None,
    "updated_at": None,
    "calculated_at": None,
}

_DATETIME_FIELDS = {"created_at", "updated_at", "calculated_at"}


def _normalize_user_payload(source: Union[User, Mapping[str, Any]], event: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for field, default in _USER_FIELDS_DEFAULTS.items():
        if isinstance(source, Mapping):
            value = source.get(field, default)
        else:
            value = getattr(source, field, default)

        if field in _DATETIME_FIELDS and value is not None:
            if isinstance(value, datetime):
                value = value.isoformat()
            else:
                value = str(value)

        payload[field] = value if value is not None else default

    payload["event"] = event
    payload["timestamp"] = datetime.utcnow().isoformat()
    return payload


def _build_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = N8N_WEBHOOK_SECRET
    return headers


async def _send_with_retry(payload: Dict[str, Any]) -> bool:
    if not N8N_WEBHOOK_URL:
        logger.warning("N8N_WEBHOOK_URL is not set; skip sending event %s", payload.get("event"))
        return False

    headers = _build_headers()
    for attempt in range(3):
        try:
            timeout = aiohttp.ClientTimeout(total=5 + attempt * 2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(N8N_WEBHOOK_URL, json=payload, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        if DEBUG:
                            logger.debug(
                                "Lead %s sent to n8n on attempt %s: %s",
                                payload.get("tg_id"),
                                attempt + 1,
                                text,
                            )
                        return True

                    logger.warning(
                        "Unexpected status %s from n8n on attempt %s: %s",
                        resp.status,
                        attempt + 1,
                        text,
                    )
        except asyncio.TimeoutError:
            logger.warning(
                "Webhook request timed out on attempt %s for lead %s",
                attempt + 1,
                payload.get("tg_id"),
            )
        except Exception:
            logger.exception(
                "Webhook request failed on attempt %s for lead %s",
                attempt + 1,
                payload.get("tg_id"),
            )

        if attempt < 2:
            await asyncio.sleep(2 ** attempt)

    return False


async def send_lead(
    source: Union[User, Mapping[str, Any]],
    event: str = "kbju_lead",
) -> bool:
    payload = _normalize_user_payload(source, event)
    return await _send_with_retry(payload)


async def test_webhook_connection() -> bool:
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "calculated_at": datetime.utcnow(),
    }

    result = await send_lead(test_payload, "kbju_lead_test")
    if not result:
        logger.warning("Webhook connectivity test failed")
    return result


class WebhookService:
    """Сервис для отправки webhook-ов в n8n."""

    @staticmethod
    async def send_lead_to_n8n(user: User, event: str = "kbju_lead") -> bool:
        return await send_lead(user, event)

    @staticmethod
    async def send_hot_lead(user_data: Mapping[str, Any], priority: str):
        payload: Dict[str, Any] = dict(user_data)
        payload["funnel_status"] = f"hotlead_{priority}"
        return await send_lead(payload, "hot_lead")

    @staticmethod
    async def send_cold_lead(user_data: Mapping[str, Any]):
        payload: Dict[str, Any] = dict(user_data)
        payload["funnel_status"] = "coldlead"
        return await send_lead(payload, "cold_lead")

    @staticmethod
    async def send_calculated_lead(user_data: Mapping[str, Any]):
        payload: Dict[str, Any] = dict(user_data)
        payload["funnel_status"] = "calculated"
        return await send_lead(payload, "calculated_lead")


class TimerService:
    """Сервис для работы с таймерами."""

    active_timers: Dict[int, asyncio.Task] = {}

    @classmethod
    async def start_calculated_timer(cls, user_id: int, delay_minutes: int = 60):
        cls.cancel_timer(user_id)

        async def timer_callback():
            try:
                await asyncio.sleep(delay_minutes * 60)
                logger.debug("Timer fired for user %s after %s minutes", user_id, delay_minutes)
            except asyncio.CancelledError:
                logger.debug("Timer for user %s was cancelled", user_id)
            finally:
                cls.active_timers.pop(user_id, None)

        task = asyncio.create_task(timer_callback())
        cls.active_timers[user_id] = task
        logger.debug("Started timer for user %s (%s minutes)", user_id, delay_minutes)

    @classmethod
    def cancel_timer(cls, user_id: int):
        task = cls.active_timers.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            logger.debug("Cancelled timer for user %s", user_id)


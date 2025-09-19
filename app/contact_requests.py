"""Вспомогательные структуры для отслеживания запросов админа связаться с лидом."""

from __future__ import annotations

import asyncio


class ContactRequestRegistry:
    """Памятная структура для хранения лидов, которым отправлено служебное сообщение."""

    def __init__(self) -> None:
        self._pending: set[int] = set()
        self._lock = asyncio.Lock()

    async def add(self, lead_id: int) -> None:
        """Отметить, что админ запросил контакт с лидом."""
        async with self._lock:
            self._pending.add(lead_id)

    async def remove(self, lead_id: int) -> None:
        """Снять отметку о запросе (например, после получения ответа)."""
        async with self._lock:
            self._pending.discard(lead_id)

    async def is_pending(self, lead_id: int) -> bool:
        """Проверить, ожидается ли ответ от лида."""
        async with self._lock:
            return lead_id in self._pending


contact_request_registry = ContactRequestRegistry()

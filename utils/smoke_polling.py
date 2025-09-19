"""Быстрая smoke-проверка настроек polling для бота."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from run import ALLOWED_UPDATES, POLLING_MODE, _log_startup_configuration


logger = logging.getLogger(__name__)

_REQUIRED_UPDATES = {"message", "callback_query"}


def _ensure_required_updates(updates: Iterable[str]) -> None:
    missing = _REQUIRED_UPDATES.difference(updates)
    if missing:
        raise SystemExit(f"Missing required allowed_updates: {sorted(missing)}")


async def _run_smoke() -> None:
    _ensure_required_updates(ALLOWED_UPDATES)
    _log_startup_configuration(ALLOWED_UPDATES)
    logger.info("Bot is ready (%s)", POLLING_MODE)
    print("Bot is ready (polling)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    asyncio.run(_run_smoke())


if __name__ == "__main__":
    main()

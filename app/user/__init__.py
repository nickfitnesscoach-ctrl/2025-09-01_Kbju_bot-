"""User-facing router assembly."""

from __future__ import annotations

from aiogram import Router

from . import contact, general, kbju, leads, lifecycle

user = Router(name="user")

for module in (general, contact, leads, kbju, lifecycle):
    module.register(user)

__all__ = ["user"]

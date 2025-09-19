# app/admin.py
from __future__ import annotations

import logging
from typing import Optional, List

from aiogram import Router, F
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from app.database.requests import get_hot_leads
from app.states import AdminStates
from app.texts import get_text, get_button_text
from app.calculator import get_goal_description, get_activity_description
from config import ADMIN_CHAT_ID
from utils.notifications import CONTACT_REQUEST_MESSAGE


# ----------------------------
# Router
# ----------------------------
admin = Router()


logger = logging.getLogger(__name__)


# ----------------------------
# Admin filter
# ----------------------------
class Admin(Filter):
    """Простой фильтр доступа по списку ID."""

    def __init__(self, admin_ids: Optional[List[int]] = None):
        # Задай свой ID здесь или передавай извне.
        self.admins = admin_ids or [ADMIN_CHAT_ID]

    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.admins)


# ----------------------------
# Helpers (formatting)
# ----------------------------
def _fmt(v, suffix: str = "") -> str:
    """Человекочитаемое значение с единицами измерения и дефолтом."""
    if v is None or v == "":
        return "не указано"
    return f"{v}{suffix}" if suffix else f"{v}"


def _username_link(username: Optional[str]) -> str:
    """HTML-ссылка на username (или заглушка)."""
    if not username:
        return "нет username"
    return f'<a href="https://t.me/{username}">@{username}</a>'


def _priority_label(code: Optional[str]) -> str:
    """Подпись направления из JSON кнопок (priority_nutrition/training/schedule)."""
    if not code:
        return "не указано"
    return get_button_text(f"priority_{code}")


def _priority_icon(score: int) -> str:
    """Визуальный индикатор приоритета."""
    if score >= 100:
        return "🎆"
    if score >= 80:
        return "🔥"
    return "🟠"


# ----------------------------
# Keyboard builder
# ----------------------------
def _lead_keyboard(current_idx: int, total_count: int, user_tg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура карточки лида (подписи из JSON)."""
    rows: list[list[InlineKeyboardButton]] = []

    # 1) Написать лиду
    rows.append([
        InlineKeyboardButton(
            text=get_button_text("write_lead"),
            url=f"tg://user?id={user_tg_id}",
        )
    ])

    # 2) Навигация (prev / next)
    nav_row: list[InlineKeyboardButton] = []
    if current_idx > 0:
        nav_row.append(
            InlineKeyboardButton(
                text=get_button_text("nav_prev"),
                callback_data=f"lead_prev_{current_idx}",
            )
        )
    if current_idx < total_count - 1:
        nav_row.append(
            InlineKeyboardButton(
                text=get_button_text("nav_next"),
                callback_data=f"lead_next_{current_idx}",
            )
        )
    if nav_row:
        rows.append(nav_row)

    # 3) Счётчик
    counter = get_text("admin.counter", current=current_idx + 1, total=total_count)
    rows.append([InlineKeyboardButton(text=counter, callback_data="noop")])

    # 4) Назад (в «админ-меню»)
    rows.append([InlineKeyboardButton(text=get_button_text("back"), callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------------
# Card renderer
# ----------------------------
async def _show_lead_card(
    target: Message | CallbackQuery,
    state: FSMContext,
    leads_list,
    index: int,
) -> None:
    """Отрисовать и показать карточку лида (по шаблону из JSON)."""
    if index < 0 or index >= len(leads_list):
        return

    lead = leads_list[index]

    # Сохраняем в FSM для навигации
    await state.update_data(leads_list=leads_list, current_index=index)
    await state.set_state(AdminStates.viewing_leads)

    # Подготовка полей
    pr_icon = _priority_icon(lead.priority_score or 0)
    gender_text = "👨 Мужской" if lead.gender == "male" else "👩 Женский"
    goal_text = get_goal_description(lead.goal or "maintenance")
    activity_text = get_activity_description(lead.activity or "moderate")

    card_text = get_text(
        "admin.lead_card",
        # Шапка
        priority_icon=pr_icon,
        index=index + 1,
        first_name=lead.first_name or "—",
        tg_id=lead.tg_id,
        username_link=_username_link(lead.username),
        priority_score=lead.priority_score or 0,
        funnel_status=lead.funnel_status or "—",
        # КБЖУ блок
        gender_text=gender_text,
        age_text=_fmt(lead.age, " лет"),
        height_text=_fmt(lead.height, " см"),
        weight_text=_fmt(lead.weight, " кг"),
        activity_text=activity_text,
        goal_text=goal_text,
        calories_text=_fmt(lead.calories, " ккал"),
        # Низ карточки
        priority_label=_priority_label(getattr(lead, "priority", None)),
        updated_at=(lead.updated_at.strftime("%d.%m %H:%M") if getattr(lead, "updated_at", None) else "—"),
    )

    kb = _lead_keyboard(index, len(leads_list), lead.tg_id)

    # Отправка/редактирование
    if isinstance(target, CallbackQuery) and target.message:
        await target.message.edit_text(card_text, reply_markup=kb, parse_mode="HTML")
    else:
        assert isinstance(target, Message)
        await target.answer(card_text, reply_markup=kb, parse_mode="HTML")


# ----------------------------
# Handlers
# ----------------------------
@admin.message(Admin(), Command("admin"))
async def admin_home(message: Message) -> None:
    """Приветственная надпись админ-панели."""
    await message.answer(get_text("admin.welcome"), parse_mode="HTML")


@admin.message(Admin(), Command("leads"))
async def admin_leads(message: Message, state: FSMContext) -> None:
    """Показать лиды (сразу открываем 1-ю карточку)."""
    leads = await get_hot_leads()
    if not leads:
        await message.answer(get_text("admin.no_hot_leads"), parse_mode="HTML")
        return
    await _show_lead_card(message, state, leads, 0)


@admin.callback_query(F.data.startswith("lead_next_"))
async def admin_next_lead(callback: CallbackQuery, state: FSMContext) -> None:
    """Следующий лид."""
    data = await state.get_data()
    leads = data.get("leads_list", [])
    idx = data.get("current_index", 0)
    next_idx = min(idx + 1, max(len(leads) - 1, 0))
    if leads:
        await _show_lead_card(callback, state, leads, next_idx)
    await callback.answer()


@admin.callback_query(F.data.startswith("lead_prev_"))
async def admin_prev_lead(callback: CallbackQuery, state: FSMContext) -> None:
    """Предыдущий лид."""
    data = await state.get_data()
    leads = data.get("leads_list", [])
    idx = data.get("current_index", 0)
    prev_idx = max(idx - 1, 0)
    if leads:
        await _show_lead_card(callback, state, leads, prev_idx)
    await callback.answer()


@admin.callback_query(F.data.startswith("lead_contact:"))
async def admin_contact_lead(callback: CallbackQuery) -> None:
    """Отправить лиду служебное сообщение по запросу админа."""
    admin_id = callback.from_user.id if callback.from_user else None
    logger.info("Admin %s pressed lead_contact button with data %s", admin_id, callback.data)

    if admin_id != ADMIN_CHAT_ID:
        logger.warning("Unauthorized lead_contact button press from %s", admin_id)
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    try:
        _, tg_id_str = callback.data.split(":", 1)
        lead_id = int(tg_id_str)
    except (AttributeError, ValueError):
        logger.warning("Invalid lead_contact payload: %s", callback.data)
        await callback.answer("Некорректные данные", show_alert=True)
        return

    bot = callback.message.bot if callback.message else None
    if bot is None:
        logger.error("Cannot access bot instance to contact lead %s", lead_id)
        await callback.answer("Ошибка отправки", show_alert=True)
        return

    try:
        await bot.send_message(chat_id=lead_id, text=CONTACT_REQUEST_MESSAGE)
    except TelegramForbiddenError as exc:
        logger.warning("Lead %s blocked bot while sending contact prompt: %s", lead_id, exc)
        await callback.answer("Бот не может написать лиду", show_alert=True)
        return
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.error("Failed to deliver contact prompt to lead %s: %s", lead_id, exc)
        await callback.answer("Не удалось отправить", show_alert=True)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while sending contact prompt to %s: %s", lead_id, exc)
        await callback.answer("Ошибка отправки", show_alert=True)
        return

    logger.info("Contact prompt delivered to lead %s", lead_id)
    await callback.answer("Сообщение отправлено")


@admin.callback_query(F.data == "admin_menu")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в «админ-меню» (просто текст-приветствие)."""
    await state.clear()
    await callback.message.edit_text(get_text("admin.welcome"), parse_mode="HTML")
    await callback.answer()

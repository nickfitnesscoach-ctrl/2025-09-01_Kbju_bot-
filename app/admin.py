from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.database.requests import get_hot_leads
from app.states import AdminStates
from app.texts import get_text, get_button_text

admin = Router()


# -------- Access filter

class Admin(Filter):
    def __init__(self) -> None:
        # TODO: вынести в ENV/конфиг при желании
        self.admins = [310151740]

    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.admins)


# -------- Commands

@admin.message(Admin(), Command("admin"))
async def cmd_admin_welcome(message: Message) -> None:
    await message.answer(get_text("admin.welcome"), parse_mode="HTML")


@admin.message(Admin(), Command("leads"))
async def cmd_hot_leads(message: Message, state: FSMContext) -> None:
    """Список горячих лидов с пагинацией."""
    hot_leads = await get_hot_leads()
    if not hot_leads:
        await message.answer(get_text("admin.no_hot_leads"), parse_mode="HTML")
        return

    await show_lead_card(message, state, hot_leads, index=0)


# -------- UI builders

def lead_navigation_keyboard(current_idx: int, total_count: int, user_tg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под карточкой лида — все тексты из JSON."""
    rows: list[list[InlineKeyboardButton]] = []

    # Написать лиду
    rows.append([
        InlineKeyboardButton(
            text=get_button_text("write_lead"),
            url=f"tg://user?id={user_tg_id}",
        )
    ])

    # Навигация
    nav_row: list[InlineKeyboardButton] = []
    if current_idx > 0:
        nav_row.append(InlineKeyboardButton(
            text=get_button_text("nav_prev"),
            callback_data=f"lead_prev_{current_idx}",
        ))
    if current_idx < total_count - 1:
        nav_row.append(InlineKeyboardButton(
            text=get_button_text("nav_next"),
            callback_data=f"lead_next_{current_idx}",
        ))
    if nav_row:
        rows.append(nav_row)

    # Счётчик и Назад
    counter = get_text("admin.counter", current=current_idx + 1, total=total_count)
    rows.append([InlineKeyboardButton(text=counter, callback_data="noop")])
    rows.append([InlineKeyboardButton(text=get_button_text("back"), callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_lead_card_text(lead, index: int) -> str:
    """
    Собираем карточку лида по шаблону admin.lead_card.
    Все человекочитаемые строки — из JSON.
    """
    first_name = lead.first_name or "—"
    username_text = f"@{lead.username}" if lead.username else "нет username"

    # Иконка приоритета
    score = int(lead.priority_score or 0)
    if score >= 100:
        priority_icon = "🎆"
    elif score >= 80:
        priority_icon = "🔥"
    else:
        priority_icon = "🟠"

    # Пол
    gender_icon = "👨" if lead.gender == "male" else "👩"
    gender_text = "Мужской" if lead.gender == "male" else "Женский"

    # Активность/цель — из словарей в JSON
    activity_key = lead.activity or "moderate"
    goal_key = lead.goal or "maintenance"
    activity_text = get_text(f"activity_descriptions.{activity_key}")
    goal_text = get_text(f"goal_descriptions.{goal_key}")

    # Дата обновления
    try:
        updated_at = lead.updated_at.strftime("%d.%m %H:%M")
    except Exception:
        updated_at = "—"

    return get_text(
        "admin.lead_card",
        index=index + 1,
        first_name=first_name,
        tg_id=lead.tg_id,
        username_text=username_text,
        priority_icon=priority_icon,
        priority_score=score,
        funnel_status=lead.funnel_status or "—",
        gender_icon=gender_icon,
        gender_text=gender_text,
        age_text=lead.age or "—",
        height_text=lead.height or "—",
        weight_text=lead.weight or "—",
        activity_text=activity_text,
        goal_text=goal_text,
        calories_text=lead.calories or "—",
        priority=lead.priority or "не указано",
        updated_at=updated_at,
    )


# -------- Card rendering

async def show_lead_card(
    message_or_callback: Message | CallbackQuery,
    state: FSMContext,
    leads_list,
    index: int,
) -> None:
    """Показать карточку одного лида (редактируем сообщение/отправляем новое)."""
    if index < 0 or index >= len(leads_list):
        return

    lead = leads_list[index]

    # Сохраняем контекст для навигации
    await state.update_data(leads_list=leads_list, current_index=index)
    await state.set_state(AdminStates.viewing_leads)

    card_text = build_lead_card_text(lead, index)
    keyboard = lead_navigation_keyboard(
        current_idx=index,
        total_count=len(leads_list),
        user_tg_id=lead.tg_id,
    )

    if isinstance(message_or_callback, CallbackQuery):
        if message_or_callback.message and isinstance(message_or_callback.message, Message):
            await message_or_callback.message.edit_text(
                card_text, reply_markup=keyboard, parse_mode="HTML"
            )
    else:
        await message_or_callback.answer(card_text, reply_markup=keyboard, parse_mode="HTML")


# -------- Navigation callbacks

@admin.callback_query(F.data.startswith("lead_next_"))
async def next_lead(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    leads_list = data.get("leads_list", [])
    current_index = data.get("current_index", 0)

    next_index = min(current_index + 1, len(leads_list) - 1)
    await show_lead_card(callback, state, leads_list, next_index)
    await callback.answer()


@admin.callback_query(F.data.startswith("lead_prev_"))
async def prev_lead(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    leads_list = data.get("leads_list", [])
    current_index = data.get("current_index", 0)

    prev_index = max(current_index - 1, 0)
    await show_lead_card(callback, state, leads_list, prev_index)
    await callback.answer()

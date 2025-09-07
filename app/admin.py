from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.calculator import get_goal_description, get_activity_description
from app.database.requests import get_hot_leads
from app.states import AdminStates
from app.texts import get_text, get_button_text

admin = Router()


class Admin(Filter):
    def __init__(self):
        self.admins = [310151740]  # ваш Telegram ID

    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in self.admins


@admin.message(Admin(), Command("admin"))
async def cmd_start(message: Message):
    await message.answer(get_text("admin.welcome"), parse_mode="HTML")


def lead_navigation_keyboard(current_idx: int, total_count: int, user_tg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для навигации по лидам (все надписи из JSON)."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Кнопка: написать лиду
    buttons.append([
        InlineKeyboardButton(
            text=get_button_text("write_lead"),
            url=f"tg://user?id={user_tg_id}",
        )
    ])

    # Навигация
    nav_buttons: list[InlineKeyboardButton] = []
    if current_idx > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text=get_button_text("nav_prev"),
                callback_data=f"lead_prev_{current_idx}",
            )
        )
    if current_idx < total_count - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text=get_button_text("nav_next"),
                callback_data=f"lead_next_{current_idx}",
            )
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    # Счётчик и Назад
    counter_text = get_text("admin.counter", current=current_idx + 1, total=total_count)
    buttons.append([InlineKeyboardButton(text=counter_text, callback_data="noop")])
    buttons.append([InlineKeyboardButton(text=get_button_text("back"), callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@admin.message(Admin(), Command("leads"))
async def cmd_hot_leads(message: Message, state: FSMContext):
    """Показать горячие лиды с пагинацией."""
    hot_leads = await get_hot_leads()

    if not hot_leads:
        await message.answer(get_text("admin.no_hot_leads"), parse_mode="HTML")
        return

    # Начинаем с первого лида
    await show_lead_card(message, state, hot_leads, 0)


async def show_lead_card(message_or_callback: Message | CallbackQuery, state: FSMContext, leads_list, index: int):
    """Показать карточку одного лида (шаблон из JSON)."""
    if index < 0 or index >= len(leads_list):
        return

    lead = leads_list[index]

    # Сохраняем данные для навигации
    await state.update_data(leads_list=leads_list, current_index=index)
    await state.set_state(AdminStates.viewing_leads)

    # Иконка приоритета (не текст, а визуальный индикатор — можно оставить в коде)
    priority_icon = "🎆" if lead.priority_score >= 100 else ("🔥" if lead.priority_score >= 80 else "🟠")

    # Отображаемые тексты (описания целей/активности — уже тянутся из JSON в calculator.py)
    goal_text = get_goal_description(lead.goal or "maintenance")
    activity_text = get_activity_description(lead.activity or "moderate")

    # Пол
    gender_label = get_text("common.gender_male") if lead.gender == "male" else get_text("common.gender_female")

    # Username и «не указано»
    username_text = f"@{lead.username}" if lead.username else get_text("common.username_not_specified")
    priority_text = lead.priority or get_text("common.not_specified")

    # Дата обновления
    updated_at = ""
    try:
        updated_at = lead.updated_at.strftime("%d.%m %H:%M")
    except Exception:
        updated_at = get_text("common.not_specified")

    # Собираем карточку из шаблона JSON
    card_text = get_text(
        "admin.lead_card",
        priority_icon=priority_icon,
        index=index + 1,
        first_name=lead.first_name or get_text("common.not_specified"),
        tg_id=lead.tg_id,
        username_text=username_text,
        priority_score=lead.priority_score,
        funnel_status=lead.funnel_status or get_text("common.not_specified"),
        gender_label=gender_label,
        age=lead.age or get_text("common.not_specified"),
        height=lead.height or 0,
        weight=lead.weight or 0,
        activity_text=activity_text,
        goal_text=goal_text,
        calories=lead.calories or 0,
        priority=priority_text,
        updated_at=updated_at,
    )

    keyboard = lead_navigation_keyboard(
        current_idx=index,
        total_count=len(leads_list),
        user_tg_id=lead.tg_id,
    )

    # Новое сообщение или редактирование
    if isinstance(message_or_callback, CallbackQuery):
        if message_or_callback.message and isinstance(message_or_callback.message, Message):
            await message_or_callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message_or_callback.answer(card_text, reply_markup=keyboard, parse_mode="HTML")


# Обработчики навигации
@admin.callback_query(F.data.startswith("lead_next_"))
async def next_lead(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    leads_list = data.get("leads_list", [])
    current_index = data.get("current_index", 0)

    next_index = min(current_index + 1, len(leads_list) - 1)
    await show_lead_card(callback, state, leads_list, next_index)
    await callback.answer()


@admin.callback_query(F.data.startswith("lead_prev_"))
async def prev_lead(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    leads_list = data.get("leads_list", [])
    current_index = data.get("current_index", 0)

    prev_index = max(current_index - 1, 0)
    await show_lead_card(callback, state, leads_list, prev_index)
    await callback.answer()

from aiogram import Router, F
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.database.requests import get_hot_leads
from app.states import AdminStates

admin = Router()


class Admin(Filter):
    def __init__(self):
        self.admins = [310151740]  # Ваш Telegram ID

    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in self.admins
    

@admin.message(Admin(), Command('admin'))
async def cmd_start(message: Message):
    await message.answer('Добро пожаловать в бот, администратор!')


def lead_navigation_keyboard(current_idx: int, total_count: int, user_tg_id: int):
    """Клавиатура для навигации по лидам"""
    buttons = []
    
    # Кнопка написать лиду
    buttons.append([InlineKeyboardButton(text="💬 Написать лиду", url=f"tg://user?id={user_tg_id}")])
    
    # Навигация
    nav_buttons = []
    if current_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Предыдущий", callback_data=f"lead_prev_{current_idx}"))
    if current_idx < total_count - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️ Следующий", callback_data=f"lead_next_{current_idx}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Счетчик и выход
    buttons.append([InlineKeyboardButton(text=f"📊 {current_idx + 1} из {total_count}", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@admin.message(Admin(), Command('leads'))
async def cmd_hot_leads(message: Message, state: FSMContext):
    """Показать горячие лиды с пагинацией"""
    hot_leads = await get_hot_leads()
    
    if not hot_leads:
        await message.answer("📈 <b>Горячих лидов нет</b>", parse_mode='HTML')
        return
    
    # Начинаем с первого лида
    await show_lead_card(message, state, hot_leads, 0)


async def show_lead_card(message_or_callback, state: FSMContext, leads_list, index: int):
    """Показать карточку одного лида"""
    if index >= len(leads_list) or index < 0:
        return
    
    lead = leads_list[index]
    
    # Сохраняем данные для навигации
    await state.update_data(leads_list=leads_list, current_index=index)
    await state.set_state(AdminStates.viewing_leads)
    
    # Формируем карточку лида
    priority_icon = "🎆" if lead.priority_score >= 100 else "🔥" if lead.priority_score >= 80 else "🟠"
    username_text = f"@{lead.username}" if lead.username else "нет username"
    
    card_text = f"""
{priority_icon} <b>Лид #{index + 1}</b>

👤 <b>{lead.first_name or 'Неизвестно'}</b>
🆔 ID: <code>{lead.tg_id}</code>
💬 Username: {username_text}
🏆 Приоритет: {lead.priority_score}
📈 Статус: {lead.funnel_status}

📊 <b>КБЖУ данные:</b>
- Пол: {'👨 Мужской' if lead.gender == 'male' else '👩 Женский'}
- Возраст: {lead.age or 'не указан'}
- Рост: {lead.height or 0} см
- Вес: {lead.weight or 0} кг
- Калории: {lead.calories or 0} ккал

🎯 Приоритет: {lead.priority or 'не указан'}
🕓 Обновлен: {lead.updated_at.strftime('%d.%m %H:%M')}
"""
    
    keyboard = lead_navigation_keyboard(
        current_idx=index,
        total_count=len(leads_list),
        user_tg_id=lead.tg_id
    )
    
    # Определяем, это новое сообщение или редактирование
    if hasattr(message_or_callback, 'edit_text'):
        await message_or_callback.edit_text(card_text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await message_or_callback.answer(card_text, reply_markup=keyboard, parse_mode='HTML')


# Обработчики навигации
@admin.callback_query(F.data.startswith("lead_next_"))
async def next_lead(callback: CallbackQuery, state: FSMContext):
    """Следующий лид"""
    data = await state.get_data()
    leads_list = data.get('leads_list', [])
    current_index = data.get('current_index', 0)
    
    next_index = min(current_index + 1, len(leads_list) - 1)
    await show_lead_card(callback, state, leads_list, next_index)
    await callback.answer()


@admin.callback_query(F.data.startswith("lead_prev_"))
async def prev_lead(callback: CallbackQuery, state: FSMContext):
    """Предыдущий лид"""
    data = await state.get_data()
    leads_list = data.get('leads_list', [])
    current_index = data.get('current_index', 0)
    
    prev_index = max(current_index - 1, 0)
    await show_lead_card(callback, state, leads_list, prev_index)
    await callback.answer()

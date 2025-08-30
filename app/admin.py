from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import Message

from app.database.requests import get_hot_leads

admin = Router()


class Admin(Filter):
    def __init__(self):
        self.admins = [310151740]  # Ваш Telegram ID

    async def __call__(self, message: Message):
        return message.from_user.id in self.admins
    

@admin.message(Admin(), Command('admin'))
async def cmd_start(message: Message):
    await message.answer('Добро пожаловать в бот, администратор!')


@admin.message(Admin(), Command('leads'))
async def cmd_hot_leads(message: Message):
    """Показать горячие лиды по приоритету"""
    hot_leads = await get_hot_leads()
    
    if not hot_leads:
        await message.answer("📈 <b>Горячих лидов нет</b>", parse_mode='HTML')
        return
    
    leads_text = "🔥 <b>Горячие лиды (по приоритету):</b>\n\n"
    
    for i, lead in enumerate(hot_leads[:10], 1):  # Показываем топ-10
        priority_icon = "🎆" if lead.priority_score >= 100 else "🔥" if lead.priority_score >= 80 else "🟠"
        username_text = f"@{lead.username}" if lead.username else "нет username"
        
        leads_text += f"{priority_icon} <b>{i}. {lead.first_name or 'Неизвестно'}</b>\n"
        leads_text += f"🆔 ID: <code>{lead.tg_id}</code>\n"
        leads_text += f"💬 {username_text}\n"
        leads_text += f"🏆 Приоритет: {lead.priority_score}\n"
        leads_text += f"📈 Статус: {lead.funnel_status}\n"
        if lead.priority:
            leads_text += f"🎨 Направление: {lead.priority}\n"
        leads_text += f"🕓 {lead.updated_at.strftime('%d.%m %H:%M')}\n\n"
    
    if len(hot_leads) > 10:
        leads_text += f"… и ещё {len(hot_leads) - 10} лидов"
    
    await message.answer(leads_text, parse_mode='HTML')

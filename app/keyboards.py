from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.texts import get_button_text


# Главное меню бота
def main_menu():
    """Главное меню с основными функциями"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("calculate_kbju"), callback_data="start_kbju")],
        [InlineKeyboardButton(text=get_button_text("my_profile"), callback_data="profile")]
    ])


# Выбор пола
def gender_keyboard():
    """Клавиатура для выбора пола"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("male"), callback_data="gender_male")],
        [InlineKeyboardButton(text=get_button_text("female"), callback_data="gender_female")]
    ])


# Уровень физической активности
def activity_keyboard():
    """Клавиатура для выбора уровня активности"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("activity_low"), callback_data="activity_low")],
        [InlineKeyboardButton(text=get_button_text("activity_moderate"), callback_data="activity_moderate")],
        [InlineKeyboardButton(text=get_button_text("activity_high"), callback_data="activity_high")],
        [InlineKeyboardButton(text=get_button_text("activity_very_high"), callback_data="activity_very_high")]
    ])


# Цели пользователя
def goal_keyboard():
    """Клавиатура для выбора цели"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("goal_weight_loss"), callback_data="goal_weight_loss")],
        [InlineKeyboardButton(text=get_button_text("goal_maintenance"), callback_data="goal_maintenance")],
        [InlineKeyboardButton(text=get_button_text("goal_weight_gain"), callback_data="goal_weight_gain")]
    ])


# Воронка лидов - основной выбор
def funnel_keyboard():
    """Клавиатура для воронки лидов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("ready_to_work"), callback_data="funnel_hot")],
        [InlineKeyboardButton(text=get_button_text("want_advice"), callback_data="funnel_cold")]
    ])


# Приоритеты для горячих лидов
def priority_keyboard():
    """Клавиатура выбора приоритета для горячих лидов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍩 Как питаться без ограничений?", callback_data="priority_nutrition")],
        [InlineKeyboardButton(text="🏋️ Хожу в зал - результата нет", callback_data="priority_training")],
        [InlineKeyboardButton(text="⏰ Нет времени", callback_data="priority_schedule")]
    ])


# Клавиатура профиля пользователя
def profile_keyboard():
    """Клавиатура для просмотра профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Пересчитать КБЖУ", callback_data="start_kbju")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


# Админ клавиатуры (если понадобятся)
def admin_menu():
    """Админ меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")]
    ])


# Клавиатура для отложенного предложения
def delayed_offer_keyboard():
    """Клавиатура для отложенного предложения после КБЖУ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("delayed_yes"), callback_data="delayed_yes")],
        [InlineKeyboardButton(text=get_button_text("delayed_no"), callback_data="delayed_no")]
    ])


# Клавиатура для запроса консультации
def consultation_contact_keyboard():
    """Клавиатура с кнопкой отправки лида для консультации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Оставить заявку", callback_data="send_lead")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


# Возврат к главному меню
def back_to_menu():
    """Кнопка возврата в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

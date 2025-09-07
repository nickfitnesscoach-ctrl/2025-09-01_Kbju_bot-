from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.texts import get_button_text


# Главное меню бота
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("calculate_kbju"), callback_data="start_kbju")],
        [InlineKeyboardButton(text=get_button_text("my_profile"), callback_data="profile")],
    ])


# Выбор пола
def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("male"), callback_data="gender_male")],
        [InlineKeyboardButton(text=get_button_text("female"), callback_data="gender_female")],
    ])


# Уровень физической активности (синхронизировано с user.py: min/low/medium/high)
def activity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("activity_min"),    callback_data="activity_min")],
        [InlineKeyboardButton(text=get_button_text("activity_low"),    callback_data="activity_low")],
        [InlineKeyboardButton(text=get_button_text("activity_medium"), callback_data="activity_medium")],
        [InlineKeyboardButton(text=get_button_text("activity_high"),   callback_data="activity_high")],
    ])


# Цели пользователя
def goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("goal_weight_loss"),  callback_data="goal_weight_loss")],
        [InlineKeyboardButton(text=get_button_text("goal_maintenance"),  callback_data="goal_maintenance")],
        [InlineKeyboardButton(text=get_button_text("goal_weight_gain"),  callback_data="goal_weight_gain")],
    ])


# Воронка лидов - основной выбор
def funnel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("ready_to_work"), callback_data="funnel_hot")],
        [InlineKeyboardButton(text=get_button_text("want_advice"),   callback_data="funnel_cold")],
    ])


# Приоритеты для горячих лидов
def priority_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("priority_nutrition"), callback_data="priority_nutrition")],
        [InlineKeyboardButton(text=get_button_text("priority_training"),  callback_data="priority_training")],
        [InlineKeyboardButton(text=get_button_text("priority_schedule"),  callback_data="priority_schedule")],
    ])


# Клавиатура профиля пользователя
def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("recalculate"), callback_data="start_kbju")],
        [InlineKeyboardButton(text=get_button_text("main_menu"),   callback_data="main_menu")],
    ])


# Админ-меню (подписи тоже из JSON)
def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("admin_stats"),     callback_data="admin_stats")],
        [InlineKeyboardButton(text=get_button_text("admin_broadcast"), callback_data="admin_broadcast")],
        [InlineKeyboardButton(text=get_button_text("admin_users"),     callback_data="admin_users")],
    ])


# Клавиатура для отложенного предложения
def delayed_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("delayed_yes"), callback_data="delayed_yes")],
        [InlineKeyboardButton(text=get_button_text("delayed_no"),  callback_data="delayed_no")],
    ])


# Клавиатура для запроса консультации
def consultation_contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("send_lead"),  callback_data="send_lead")],
        [InlineKeyboardButton(text=get_button_text("main_menu"),   callback_data="main_menu")],
    ])


# Возврат к главному меню
def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_button_text("main_menu"), callback_data="main_menu")],
    ])

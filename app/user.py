"""
Основной flow для пользователей Fitness Bot
Включает полный цикл: регистрация -> КБЖУ -> воронка лидов -> webhook
"""

import asyncio
import html
import logging
from datetime import datetime
from functools import wraps
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, URLInputFile

from app.calculator import KBJUCalculator, get_activity_description, get_goal_description
from app.database.requests import get_user, set_user, update_user_data, update_user_status
from app.keyboards import (
    main_menu, gender_keyboard, activity_keyboard, goal_keyboard,
    priority_keyboard, profile_keyboard, delayed_offer_keyboard,
    consultation_contact_keyboard, back_to_menu
)
from app.states import KBJUStates
from app.texts import get_text
from app.webhook import TimerService, WebhookService
from app.constants import (
    USER_REQUESTS_LIMIT, USER_REQUESTS_WINDOW, DEFAULT_CALCULATED_TIMER_DELAY,
    DELAYED_OFFER_DELAY, PRIORITY_SCORES, VALIDATION_LIMITS, MAX_TEXT_LENGTH,
    DB_OPERATION_TIMEOUT, FUNNEL_STATUSES
)
from config import CHANNEL_URL

logger = logging.getLogger(__name__)

# Rate limiting storage
user_requests = {}

user = Router()


# Декораторы для безопасности и обработки ошибок
def rate_limit(func):
    """Декоратор для ограничения частоты запросов"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Получаем user_id из callback или message
        user_id = None
        if args and hasattr(args[0], 'from_user') and args[0].from_user:
            user_id = args[0].from_user.id
        
        if user_id:
            now = datetime.utcnow().timestamp()
            if user_id not in user_requests:
                user_requests[user_id] = []
            
            # Очищаем старые запросы
            user_requests[user_id] = [
                req_time for req_time in user_requests[user_id] 
                if now - req_time < USER_REQUESTS_WINDOW
            ]
            
            # Проверяем лимит
            if len(user_requests[user_id]) >= USER_REQUESTS_LIMIT:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return
            
            user_requests[user_id].append(now)
        
        return await func(*args, **kwargs)
    return wrapper


def error_handler(func):
    """Декоратор для обработки ошибок"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TelegramBadRequest as e:
            logger.error(f"Telegram error in {func.__name__}: {e}")
            # Игнорируем ошибку "message is not modified" - это нормально
            if "message is not modified" in str(e):
                # Просто отвечаем на callback без изменений
                if args and hasattr(args[0], 'answer'):
                    try:
                        await args[0].answer()
                    except (TelegramBadRequest, TelegramNetworkError) as e:
                        logger.warning("Send answer failed: %s", e)
                return
            
            # Пробуем отправить новое сообщение вместо редактирования
            if args and hasattr(args[0], 'message'):
                try:
                    await args[0].message.answer(
                        "❌ Произошла ошибка. Попробуйте еще раз.",
                        reply_markup=back_to_menu()
                    )
                except Exception as e:
                    logger.exception("Unhandled UI error: %s", e)
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited by Telegram: {e}")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            if args and hasattr(args[0], 'message'):
                try:
                    await args[0].message.answer(
                        "❌ Произошла ошибка. Попробуйте еще раз.",
                        reply_markup=back_to_menu()
                    )
                except Exception as e:
                    logger.exception("Unhandled UI error: %s", e)
    return wrapper


def validate_user_data(data: dict[str, Any]) -> bool:
    """Валидация пользовательских данных"""
    if not data:
        return False
    
    # Проверяем возраст
    age = data.get('age')
    if not age or not (VALIDATION_LIMITS['age']['min'] <= age <= VALIDATION_LIMITS['age']['max']):
        return False
    
    # Проверяем вес
    weight = data.get('weight')
    if not weight or not (VALIDATION_LIMITS['weight']['min'] <= weight <= VALIDATION_LIMITS['weight']['max']):
        return False
    
    # Проверяем рост
    height = data.get('height')
    if not height or not (VALIDATION_LIMITS['height']['min'] <= height <= VALIDATION_LIMITS['height']['max']):
        return False
    
    # Проверяем обязательные поля
    required_fields = ['gender', 'activity', 'goal']
    for field in required_fields:
        if field not in data or not data[field]:
            return False
    
    return True


def sanitize_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Санитизация текста для безопасности"""
    if not text:
        return ""
    
    # Экранируем HTML
    text = html.escape(str(text))
    
    # Ограничиваем длину
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text


async def send_delayed_offer(user_id: int, chat_id: int):
    """Отправить задержанное сообщение с предложением"""
    from aiogram import Bot

    from config import TOKEN
    
    # Задержка
    await asyncio.sleep(DELAYED_OFFER_DELAY)
    
    try:
        bot = Bot(token=TOKEN)
        
        offer_text = get_text("delayed_offer")
        
        await bot.send_message(
            chat_id=chat_id,
            text=offer_text,
            reply_markup=delayed_offer_keyboard(),
            parse_mode='HTML'
        )
        
        await bot.session.close()
        
    except Exception as e:
        logger.error(f"Error sending delayed offer: {e}")


async def safe_db_operation(operation, *args, **kwargs):
    """Безопасное выполнение операций с БД"""
    try:
        # Добавляем timeout
        return await asyncio.wait_for(operation(*args, **kwargs), timeout=DB_OPERATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(f"Database operation timeout: {operation.__name__}")
        return None
    except Exception as e:
        logger.error(f"Database operation error: {e}")
        return None


def get_advice_by_goal(goal: str) -> str:
    """Получить советы в зависимости от цели"""
    return get_text(f"advice.{goal}")


async def calculate_and_save_kbju(user_id: int, user_data: dict) -> dict:
    """Рассчитать КБЖУ и сохранить в БД"""
    # Рассчитываем КБЖУ
    kbju = KBJUCalculator.calculate_kbju(
        gender=user_data['gender'],
        age=user_data['age'], 
        weight=user_data['weight'],
        height=user_data['height'],
        activity=user_data['activity'],
        goal=user_data['goal']
    )
    
    # Сохраняем в БД
    await update_user_data(
        tg_id=user_id,
        **user_data,
        **kbju,
        funnel_status=FUNNEL_STATUSES['calculated'],
        calculated_at=datetime.utcnow(),
        priority_score=PRIORITY_SCORES['new']
    )
    
    return kbju


async def show_kbju_results(callback: CallbackQuery, kbju: dict, goal: str):
    """Показать результаты расчета КБЖУ"""
    goal_text = get_goal_description(goal)
    
    result_text = f"""
🎉 <b>Твоя персональная норма КБЖУ для {goal_text.lower()}:</b>

🔥 <b>Калории:</b> {kbju['calories']} ккал/день
🥩 <b>Белки:</b> {kbju['proteins']} г
🥑 <b>Жиры:</b> {kbju['fats']} г  
🍞 <b>Углеводы:</b> {kbju['carbs']} г
"""
    
    await callback.message.edit_text(
        result_text,
        parse_mode='HTML'
    )


async def start_funnel_timer(user_id: int):
    """Запустить таймер воронки лидов"""
    await TimerService.start_calculated_timer(user_id, delay_minutes=DEFAULT_CALCULATED_TIMER_DELAY)


async def schedule_delayed_offer(user_id: int, chat_id: int):
    """Запланировать отложенное предложение"""
    asyncio.create_task(send_delayed_offer(user_id, chat_id))


async def send_welcome_sequence(message: Message):
    """Отправить последовательность приветствия: фото + текст"""
    # Сначала отправляем фото без caption
    try:
        photo_url = get_text("coach_photo_url")
        photo = URLInputFile(photo_url)
        await message.answer_photo(photo=photo)
    except TelegramBadRequest as e:
        logger.error(f"Error sending photo: {e}")
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
    
    # Затем отправляем приветственное сообщение с клавиатурой
    try:
        welcome_text = get_text("welcome")
        await message.answer(
            welcome_text,
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        logger.error(f"Error sending welcome text: {e}")
        # Fallback сообщение
        await message.answer(
            "Добро пожаловать!",
            reply_markup=main_menu()
        )


@user.message(CommandStart())
@rate_limit
@error_handler
async def cmd_start(message: Message):
    """Команда /start - приветствие с фото и главное меню"""
    if not message.from_user or not message.from_user.id:
        logger.warning("Received start command without user info")
        return
    
    # Санитизируем данные пользователя
    username = sanitize_text(message.from_user.username or "", 50)
    first_name = sanitize_text(message.from_user.first_name or "Пользователь", 50)
    
    # Безопасно сохраняем пользователя
    result = await safe_db_operation(
        set_user,
        tg_id=message.from_user.id,
        username=username,
        first_name=first_name
    )
    
    if result is False:  # Ошибка сохранения
        await message.answer(
            "❌ <b>Временная ошибка</b>\n\n"
            "Попробуйте еще раз через несколько секунд.",
            parse_mode='HTML'
        )
        return
    
    # Отправляем последовательность приветствия
    await send_welcome_sequence(message)


@user.callback_query(F.data == "main_menu")
@rate_limit
@error_handler
async def show_main_menu(callback: CallbackQuery):
    """Показать главное меню"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    await callback.message.edit_text(
        get_text("main_menu"),
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data == "profile")
@rate_limit
@error_handler
async def show_profile(callback: CallbackQuery):
    """Показать профиль пользователя"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    user_data = await safe_db_operation(get_user, callback.from_user.id)
    
    if not user_data or not user_data.calories:
        await callback.message.edit_text(
            get_text("profile.no_data"),
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        await callback.answer()
        return
    
    # Формируем текст профиля с защитой от None
    try:
        goal_text = get_goal_description(user_data.goal or 'maintenance')
        activity_text = get_activity_description(user_data.activity or 'moderate')
        
        # Безопасное форматирование даты
        calc_date = "не указано"
        if user_data.calculated_at:
            try:
                calc_date = user_data.calculated_at.strftime('%d.%m.%Y')
            except Exception:
                calc_date = "не указано"
        
        profile_text = f"""
👤 <b>Твой профиль</b>

📊 <b>Данные:</b>
• Пол: {'👨 Мужской' if user_data.gender == 'male' else '👩 Женский'}
• Возраст: {user_data.age or 0} лет
• Рост: {user_data.height or 0} см
• Вес: {user_data.weight or 0} кг
• Активность: {activity_text}
• Цель: {goal_text}

🔥 <b>Твоя норма КБЖУ:</b>
• Калории: {user_data.calories or 0} ккал/день
• Белки: {user_data.proteins or 0} г
• Жиры: {user_data.fats or 0} г  
• Углеводы: {user_data.carbs or 0} г

📅 Рассчитано: {calc_date}
"""
        
        await callback.message.edit_text(
            profile_text,
            reply_markup=profile_keyboard(),
            parse_mode='HTML'
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error formatting profile: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка отображения профиля</b>\n\n"
            "Попробуйте еще раз.",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        await callback.answer()


@user.callback_query(F.data == "start_kbju")
@rate_limit
@error_handler
async def start_kbju_flow(callback: CallbackQuery, state: FSMContext):
    """Начать расчет КБЖУ"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    # Отменяем таймер если пользователь возвращается
    try:
        TimerService.cancel_timer(callback.from_user.id)
    except Exception as e:
        logger.error(f"Error canceling timer: {e}")
    
    await callback.message.edit_text(
        get_text("kbju_start"),
        reply_markup=gender_keyboard(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data.startswith("gender_"))
@rate_limit
@error_handler
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    if not callback.from_user or not callback.from_user.id or not callback.message or not callback.data:
        return
        
    try:
        gender = callback.data.split("_")[1]  # male/female
        if gender not in ['male', 'female']:
            logger.warning(f"Invalid gender: {gender}")
            return
            
        await state.update_data(gender=gender)
        
        gender_text = "мужской" if gender == "male" else "женский"
        
        await callback.message.edit_text(
            f"👤 Пол: <b>{gender_text}</b>\n\n"
            "🎂 Сколько тебе лет?\n"
            "<i>Введи возраст числом (например: 25)</i>",
            parse_mode='HTML'
        )
        await state.set_state(KBJUStates.waiting_age)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error processing gender: {e}")
        await callback.answer("Ошибка обработки данных")


@user.message(KBJUStates.waiting_age)
@rate_limit
@error_handler
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста"""
    if not message.from_user or not message.from_user.id or not message.text:
        return
        
    # Санитизируем ввод
    age_text = sanitize_text(message.text.strip(), 10)
    
    try:
        age = int(age_text)
        if 15 <= age <= 80:
            await state.update_data(age=age)
            
            await message.answer(
                f"🎂 Возраст: <b>{age} лет</b>\n\n"
                "⚖️ Какой у тебя вес в кг?\n"
                "<i>Введи число (например: 70 или 65.5)</i>",
                parse_mode='HTML'
            )
            await state.set_state(KBJUStates.waiting_weight)
        else:
            await message.answer(
                "❌ <b>Возраст должен быть от 15 до 80 лет</b>\n\n"
                "Попробуй еще раз:",
                parse_mode='HTML'
            )
    except (ValueError, TypeError):
        await message.answer(
            "❌ <b>Введи возраст числом</b>\n\n"
            "Например: <code>25</code>",
            parse_mode='HTML'
        )


@user.message(KBJUStates.waiting_weight)
@rate_limit
@error_handler
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    if not message.from_user or not message.from_user.id or not message.text:
        return
        
    # Санитизируем ввод
    weight_text = sanitize_text(message.text.strip(), 10)
    
    try:
        weight = float(weight_text.replace(',', '.'))
        if 30 <= weight <= 200:
            await state.update_data(weight=weight)
            
            await message.answer(
                f"⚖️ Вес: <b>{weight} кг</b>\n\n"
                "📏 Какой у тебя рост в см?\n"
                "<i>Введи число (например: 175)</i>",
                parse_mode='HTML'
            )
            await state.set_state(KBJUStates.waiting_height)
        else:
            await message.answer(
                "❌ <b>Вес должен быть от 30 до 200 кг</b>\n\n"
                "Попробуй еще раз:",
                parse_mode='HTML'
            )
    except (ValueError, TypeError):
        await message.answer(
            "❌ <b>Введи вес числом</b>\n\n"
            "Например: <code>70</code> или <code>65.5</code>",
            parse_mode='HTML'
        )


@user.message(KBJUStates.waiting_height)
@rate_limit
@error_handler
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    if not message.from_user or not message.from_user.id or not message.text:
        return
        
    # Санитизируем ввод
    height_text = sanitize_text(message.text.strip(), 10)
    
    try:
        height = int(height_text)
        if 140 <= height <= 220:
            await state.update_data(height=height)
            
            # ИСПРАВЛЕНО: Используем get_text() вместо хардкода
            await message.answer(
                get_text("questions.activity", height=height),
                reply_markup=activity_keyboard(),
                parse_mode='HTML'
            )
        else:
            await message.answer(
                "❌ <b>Рост должен быть от 140 до 220 см</b>\n\n"
                "Попробуй еще раз:",
                parse_mode='HTML'
            )
    except (ValueError, TypeError):
        await message.answer(
            "❌ <b>Введи рост числом</b>\n\n"
            "Например: <code>175</code>",
            parse_mode='HTML'
        )


@user.callback_query(F.data.startswith("activity_"))
@rate_limit
@error_handler
async def process_activity(callback: CallbackQuery, state: FSMContext):
    """Обработка уровня активности"""
    if not callback.from_user or not callback.from_user.id or not callback.message or not callback.data:
        return
        
    try:
        activity_raw = callback.data.split("_", 1)[1]  # min/low/medium/high
        
        # Маппинг новых значений на существующие в калькуляторе
        activity_mapping = {
            'min': 'low',        # Минимальная -> Низкая в калькуляторе  
            'low': 'low',        # Низкая -> Низкая
            'medium': 'moderate', # Средняя -> Умеренная
            'high': 'high'       # Высокая -> Высокая
        }
        
        activity = activity_mapping.get(activity_raw, 'moderate')
        await state.update_data(activity=activity)
        
        # Текстовые описания для отображения
        activity_display_mapping = {
            'min': '📉 Минимальная',
            'low': '🚶 Низкая', 
            'medium': '🏋️ Средняя',
            'high': '🔥 Высокая'
        }
        
        activity_text = activity_display_mapping.get(activity_raw, '🚶 Умеренная')
        
        await callback.message.edit_text(
            f"🏃‍♂️ Активность: <b>{activity_text}</b>\n\n"
            "🎯 <b>Какая у тебя основная цель?</b>",
            reply_markup=goal_keyboard(),
            parse_mode='HTML'
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error processing activity: {e}")
        await callback.answer("Ошибка обработки данных")


@user.callback_query(F.data.startswith("goal_"))
@rate_limit
@error_handler
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Финальный этап - расчет и показ КБЖУ"""
    if not callback.from_user or not callback.from_user.id or not callback.message or not callback.data:
        return
        
    try:
        goal = callback.data.split("_", 1)[1]  # weight_loss/maintenance/weight_gain
        data = await state.get_data()
        data['goal'] = goal
        
        # Рассчитываем КБЖУ и сохраняем в БД
        kbju = await calculate_and_save_kbju(callback.from_user.id, data)
        
        # Запускаем таймер воронки лидов
        await start_funnel_timer(callback.from_user.id)
        
        # Показываем результаты пользователю
        await show_kbju_results(callback, kbju, goal)
        await callback.answer()
        await state.clear()
        
        # Запускаем задержанное предложение
        await schedule_delayed_offer(callback.from_user.id, callback.message.chat.id)
        
    except Exception as e:
        logger.error(f"Error in process_goal: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка при расчете КБЖУ</b>\n\n"
            "Попробуй начать заново через /start",
            reply_markup=back_to_menu(),
            parse_mode='HTML'
        )
        await callback.answer()
        await state.clear()


@user.callback_query(F.data == "delayed_yes")
@rate_limit
@error_handler
async def process_delayed_yes(callback: CallbackQuery):
    """Обработка положительного ответа на отложенное предложение - выбор направления"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    # Отменяем таймер - пользователь продолжил воронку
    TimerService.cancel_timer(callback.from_user.id)
    
    # Показываем выбор направления
    priorities_text = get_text("hot_lead_priorities")
    
    await callback.message.edit_text(
        priorities_text,
        reply_markup=priority_keyboard(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data == "delayed_no")
@rate_limit
@error_handler
async def process_delayed_no(callback: CallbackQuery):
    """Обработка отрицательного ответа на отложенное предложение - советы"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    # Обновляем статус на холодный лид
    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES['coldlead_delayed'],
        priority_score=PRIORITY_SCORES['coldlead_delayed']
    )
    
    # Отправляем данные в webhook
    user_data = await get_user(callback.from_user.id)
    if user_data:
        user_dict = _user_to_dict(user_data)
        await WebhookService.send_cold_lead(user_dict)
    
    # Показываем персональные советы
    advice_text = get_advice_by_goal(user_data.goal if user_data else 'maintenance')
    
    tips_text = f"""
💡 <b>Персональные советы для твоей цели:</b>

{advice_text}

📲 <b>Больше полезного контента в нашем канале:</b>
{CHANNEL_URL or '@fitness_channel'}

🔄 Если захочешь серьёзно заняться результатом - возвращайся!
"""
    
    await callback.message.edit_text(
        tips_text,
        reply_markup=back_to_menu(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data == "send_lead")
@rate_limit
@error_handler
async def process_lead_request(callback: CallbackQuery):
    """Обработка кнопки Оставить заявку для консультации"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    # Обновляем статус на горячий лид с высоким приоритетом
    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES['hotlead_consultation'],
        priority_score=PRIORITY_SCORES['consultation_request']
    )
    
    # Отправляем данные в webhook
    user_data = await get_user(callback.from_user.id)
    if user_data:
        user_dict = _user_to_dict(user_data)
        await WebhookService.send_hot_lead(user_dict, 'consultation_request')
    
    success_text = """
✅ <b>Отлично! Заявка отправлена!</b>

👤 Твой ID: {user_id}
💬 Твой username: @{username}

✨ Я свяжусь с тобой в течение дня для обсуждения бесплатной консультации!

💪 Готовься к системному прорыву к своей цели!
""".format(
        user_id=callback.from_user.id,
        username=callback.from_user.username or 'не указан'
    )
    
    await callback.message.edit_text(
        success_text,
        reply_markup=back_to_menu(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data.startswith("priority_"))
@rate_limit
@error_handler
async def process_priority(callback: CallbackQuery):
    """Обработка выбора приоритета и показ оффера консультации"""
    if not callback.from_user or not callback.from_user.id or not callback.message or not callback.data:
        return
        
    priority = callback.data.split("_")[1]  # nutrition/training/schedule
    
    # Обновляем статус на hotlead с направлением
    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES['hotlead_delayed'],
        priority=priority,
        priority_score=PRIORITY_SCORES['hotlead_delayed']
    )
    
    # Отправляем данные в webhook
    user_data = await get_user(callback.from_user.id)
    if user_data:
        user_dict = _user_to_dict(user_data)
        await WebhookService.send_hot_lead(user_dict, priority)
    
    # Показываем оффер консультации
    consultation_text = get_text("consultation_offer")
    
    await callback.message.edit_text(
        consultation_text,
        reply_markup=consultation_contact_keyboard(),
        parse_mode='HTML'
    )
    await callback.answer()


@user.callback_query(F.data == "funnel_cold") 
@rate_limit
@error_handler
async def process_cold_lead(callback: CallbackQuery):
    """Холодный лид - хочет советы"""
    if not callback.from_user or not callback.from_user.id or not callback.message:
        return
        
    # Отменяем таймер - пользователь продолжил воронку
    TimerService.cancel_timer(callback.from_user.id)
    
    # Обновляем статус на coldlead
    await update_user_status(
        tg_id=callback.from_user.id,
        status=FUNNEL_STATUSES['coldlead'],
        priority_score=PRIORITY_SCORES['coldlead']
    )
    
    # Получаем данные пользователя и отправляем в n8n
    user_data = await get_user(callback.from_user.id)
    if user_data:
        user_dict = _user_to_dict(user_data)
        await WebhookService.send_cold_lead(user_dict)
    
    # Показываем персональные советы
    advice_text = get_advice_by_goal(user_data.goal if user_data else 'maintenance')
    
    await callback.message.edit_text(
        f"💡 <b>Персональные советы для твоей цели:</b>\n\n{advice_text}\n\n"
        f"📢 <b>Больше полезного контента в нашем канале:</b>\n{CHANNEL_URL or '@fitness_channel'}\n\n"
        "🔄 Если захочешь серьезно заняться результатом - возвращайся, поможем составить полный план!",
        reply_markup=back_to_menu(),
        parse_mode='HTML'
    )


# Вспомогательные функции

def _user_to_dict(user) -> dict:
    """Конвертировать объект User в словарь для webhook"""
    if not user:
        return {}
        
    return {
        'tg_id': user.tg_id or 0,
        'username': user.username or '',
        'first_name': user.first_name or '',
        'gender': user.gender or '',
        'age': user.age or 0,
        'weight': user.weight or 0.0,
        'height': user.height or 0,
        'activity': user.activity or '',
        'goal': user.goal or '',
        'calories': user.calories or 0,
        'proteins': user.proteins or 0,
        'fats': user.fats or 0,
        'carbs': user.carbs or 0
    }

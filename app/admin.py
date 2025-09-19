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
    ForceReply,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from app.database.requests import get_hot_leads
from app.contact_requests import contact_request_registry
from app.states import AdminStates
from app.texts import get_text, get_button_text, set_media_id
from app.calculator import get_goal_description, get_activity_description
from config import ADMIN_CHAT_ID
from utils.notifications import CONTACT_REQUEST_MESSAGE

# ----------------------------
# Router
# ----------------------------
admin = Router()

logger = logging.getLogger(__name__)

_missing_admin_id_logged = False


def _is_authorized_admin(message: Message) -> bool:
    """Проверка, что сообщение пришло из приватного чата с админом."""
    global _missing_admin_id_logged

    if ADMIN_CHAT_ID is None:
        if not _missing_admin_id_logged:
            logger.warning("ADMIN_CHAT_ID is not configured; admin media handlers disabled")
            _missing_admin_id_logged = True
        return False

    if not message.from_user or message.from_user.id != ADMIN_CHAT_ID:
        return False

    if message.chat.type != "private" or message.chat.id != ADMIN_CHAT_ID:
        return False

    return True


logger = logging.getLogger(__name__)


# ----------------------------
# Admin filter
# ----------------------------
class Admin(Filter):
    """Простой фильтр доступа по списку ID."""

    def __init__(self, admin_ids: Optional[List[int]] = None):
        # Задай свой ID здесь или передавай извне.
        self.admins = admin_ids or [ADMIN_CHAT_ID]
        if admin_ids is not None:
            self.admins = admin_ids
        else:
            self.admins = []
            if ADMIN_CHAT_ID is not None:
                self.admins.append(ADMIN_CHAT_ID)

    async def __call__(self, message: Message) -> bool:
        user_id = message.from_user.id if message.from_user else None
        return bool(user_id and user_id in self.admins)


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
# Admin menu text
# ----------------------------
def _admin_menu_text() -> str:
    """Текст приветствия с перечнем доступных команд."""

    base = get_text("admin.welcome")
    commands: list[tuple[str, str]] = [
        ("/admin", "показать эту подсказку"),
        ("/leads", "список горячих лидов"),
        ("/set_coach_photo", "подсказка по обновлению приветственного фото"),
        ("/photo_id", "показать file_id фото из сообщения-реплая"),
    ]

    lines = [base, "", "Доступные команды:"]
    lines.extend(f"{command} — {description}" for command, description in commands)
    return "\n".join(lines)


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
    await state.update_data(leads_list=leads_list, current_index=index, reply_target_id=None)
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
    await message.answer(_admin_menu_text(), parse_mode="HTML")


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
        await bot.send_message(
            chat_id=lead_id,
            text=CONTACT_REQUEST_MESSAGE,
            reply_markup=ForceReply(input_field_placeholder="Напишите сообщение админу"),
        )
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
    await contact_request_registry.add(lead_id)
    await callback.answer("Сообщение отправлено")


async def _restore_reply_state(state: FSMContext) -> None:
    """Вернуть FSM в режим просмотра лидов и очистить контекст ответа."""

    data = await state.get_data()
    leads_list = data.get("leads_list")
    current_index = data.get("current_index")

    if leads_list is not None and current_index is not None:
        await state.set_state(AdminStates.viewing_leads)
        await state.update_data(reply_target_id=None)
    else:
        await state.clear()


@admin.callback_query(F.data.startswith("lead_reply:"))
async def admin_reply_lead(callback: CallbackQuery, state: FSMContext) -> None:
    """Подготовить отправку сообщения лиду от имени бота."""

    admin_id = callback.from_user.id if callback.from_user else None
    logger.info("Admin %s pressed lead_reply button with data %s", admin_id, callback.data)

    if admin_id != ADMIN_CHAT_ID:
        logger.warning("Unauthorized lead_reply button press from %s", admin_id)
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    try:
        _, tg_id_str = callback.data.split(":", 1)
        lead_id = int(tg_id_str)
    except (AttributeError, ValueError):
        logger.warning("Invalid lead_reply payload: %s", callback.data)
        await callback.answer("Некорректные данные", show_alert=True)
        return

    await state.update_data(reply_target_id=lead_id)
    await state.set_state(AdminStates.lead_reply)

    prompt = (
        "Напишите сообщение, и бот отправит его пользователю.\n"
        "Команда /cancel или слово 'отмена' — чтобы отменить."
    )
    if callback.message:
        await callback.message.answer(prompt)

    await callback.answer("Введите текст сообщения")


@admin.message(Admin(), AdminStates.lead_reply)
async def admin_send_lead_reply(message: Message, state: FSMContext) -> None:
    """Отправить сообщение выбранному лиду от имени бота."""

    data = await state.get_data()
    lead_id = data.get("reply_target_id")

    if message.text and message.text.lower().strip() in {"/cancel", "отмена"}:
        await _restore_reply_state(state)
        await message.answer("Отправка сообщения отменена.")
        return

    if not lead_id:
        logger.warning("Lead reply requested without target in state")
        await message.answer("Не выбран лид для ответа.")
        await state.clear()
        return

    logger.info("Admin %s is sending reply to lead %s", message.from_user.id if message.from_user else None, lead_id)

    try:
        await message.send_copy(chat_id=lead_id)
    except TypeError:
        if message.text:
            try:
                await message.bot.send_message(chat_id=lead_id, text=message.text)
            except TelegramForbiddenError as exc:
                logger.warning("Lead %s blocked bot during reply: %s", lead_id, exc)
                await message.answer("Бот не может написать этому пользователю.")
                await _restore_reply_state(state)
                return
            except (TelegramBadRequest, TelegramNetworkError) as exc:
                logger.error("Failed to send text reply to lead %s: %s", lead_id, exc)
                await message.answer("Не удалось отправить сообщение.")
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error while sending text reply to %s: %s", lead_id, exc)
                await message.answer("Произошла ошибка при отправке.")
                return
        else:
            await message.answer("Этот тип сообщения пока не поддерживается.")
            return
    except TelegramForbiddenError as exc:
        logger.warning("Lead %s blocked bot during reply: %s", lead_id, exc)
        await message.answer("Бот не может написать этому пользователю.")
        await _restore_reply_state(state)
        return
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        logger.error("Failed to deliver reply to lead %s: %s", lead_id, exc)
        await message.answer("Не удалось отправить сообщение.")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while sending reply to %s: %s", lead_id, exc)
        await message.answer("Произошла ошибка при отправке.")
        return

    await message.answer("Сообщение отправлено.")
    await _restore_reply_state(state)


@admin.callback_query(F.data == "admin_menu")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в «админ-меню» (просто текст-приветствие)."""
    await state.clear()
    await callback.message.edit_text(_admin_menu_text(), parse_mode="HTML")
    await callback.answer()


# ----------------------------
# Media helpers
# ----------------------------


@admin.message(Command("set_coach_photo"))
async def admin_set_coach_photo(message: Message) -> None:
    """Подсказка по обновлению приветственного фото."""
    if not _is_authorized_admin(message):
        await message.answer("Недостаточно прав")
        return

    await message.answer("Пришлите фото одним сообщением")


@admin.message(Command("photo_id"))
async def admin_photo_id(message: Message) -> None:
    """Показать file_id фото из сообщения-реплая."""
    if not _is_authorized_admin(message):
        await message.answer("Недостаточно прав")
        return

    reply = message.reply_to_message
    if not reply or not reply.photo:
        await message.answer("Эта команда работает в ответ на сообщение с фото")
        return

    await message.answer(f"file_id: {reply.photo[-1].file_id}")


@admin.message(F.photo)
async def admin_receive_photo(message: Message) -> None:
    """Сохранить file_id присланного фото и ответить администратору."""
    if not _is_authorized_admin(message):
        await message.answer("Недостаточно прав")
        return

    largest_photo = message.photo[-1]
    file_id = largest_photo.file_id

    await message.answer(f"file_id: {file_id}")

    try:
        set_media_id("coach_photo_file_id", file_id)
        logger.debug("coach_photo_file_id saved via admin photo message")
    except Exception as exc:
        logger.error("Failed to save coach photo file_id: %s", exc)
        await message.answer("Не удалось сохранить file_id, попробуйте позже.")

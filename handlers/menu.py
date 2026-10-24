"""Обработчики главного inline-меню."""

import logging
import math
from pathlib import Path

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.filters import Command

from config import BOT_NAME
from permissions import is_admin_user
from database import get_user, is_in_waitlist, get_waitlist_position
from keyboards import main_inline_menu, support_keyboard
from handlers.progress import render_progress

router = Router()
logger = logging.getLogger(__name__)


async def _edit_message(callback: CallbackQuery, text: str, **kwargs):
    """Редактирует текст, а для сообщений с фото отправляет новое."""
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as error:
        if "no text in the message to edit" not in str(error):
            raise
        await callback.message.answer(text, **kwargs)


async def show_main_menu(message: Message, with_photo: bool = False):
    from database import get_user
    user = await get_user(message.from_user.id)
    is_admin = is_admin_user(message.from_user.id)

    if user and user["status"] == "active":
        text = (
            f"С возвращением, {message.from_user.first_name}.\n\n"
            f"Подписка активна. Управление подпиской и подключением — в приложении."
        )
    elif user and user["status"] == "pending":
        text = "Заявка на рассмотрении. Администратор проверит её. Статус — в приложении."
    else:
        text = (
            f"Привет, {message.from_user.first_name}.\n\n"
            f"Это бот бесплатных подписок {BOT_NAME}.\n\n"
            f"Открой приложение, чтобы получить подписку и подключиться."
        )

    keyboard = main_inline_menu(is_admin)

    if with_photo:
        logo_path = (
            Path(__file__).resolve().parents[1]
            / "brand"
            / "png"
            / "skrepnet-cover-1280x640.png"
        )
        if logo_path.is_file():
            try:
                await message.answer_photo(
                    FSInputFile(logo_path),
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                logger.warning(
                    "Не удалось отправить приветственное фото",
                    exc_info=True,
                )

    # Отправляем ТОЛЬКО inline-меню с WebApp
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Для админа: все функции доступны в приложении."""
    if not is_admin_user(message.from_user.id):
        return

    await message.answer(
        "Все функции администратора доступны в приложении.",
        reply_markup=main_inline_menu(True)
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню."""
    is_admin = is_admin_user(callback.from_user.id)

    await _edit_message(callback,
        "<b>Главное меню</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=main_inline_menu(is_admin)
    )
    await callback.answer()


@router.callback_query(F.data == "menu_get_sub")
async def menu_get_sub(callback: CallbackQuery):
    await _handle_get_sub(callback)


@router.callback_query(F.data == "menu_my_sub")
async def menu_my_sub(callback: CallbackQuery):
    await _handle_my_sub(callback)


@router.callback_query(F.data == "menu_invite")
async def menu_invite(callback: CallbackQuery):
    await _handle_invite(callback)


@router.callback_query(F.data == "menu_invite_no_tg")
async def menu_invite_no_tg(callback: CallbackQuery):
    await _handle_invite_no_tg(callback)


@router.callback_query(F.data == "menu_support")
async def menu_support(callback: CallbackQuery):
    from config import SUPPORT_USERNAME
    await _edit_message(callback,
        f"<b>Техподдержка {BOT_NAME}</b>\n\n"
        "Если у тебя возникли вопросы, проблемы с подключением "
        "или ты хочешь сообщить о сбое — напиши нам.\n\n"
        f"Канал техподдержки: @{SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=support_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "menu_docs")
async def menu_docs(callback: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from docs_config import DOCS
    await _edit_message(callback,
        f"<b>Документы {BOT_NAME}</b>\n\n"
        "Выбери документ для просмотра:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=DOCS["rules"]["title"], url=DOCS["rules"]["url"])],
            [InlineKeyboardButton(text=DOCS["privacy"]["title"], url=DOCS["privacy"]["url"])],
            [InlineKeyboardButton(text=DOCS["terms"]["title"], url=DOCS["terms"]["url"])],
            [InlineKeyboardButton(text="В главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_progress")
async def menu_progress(callback: CallbackQuery):
    from keyboards import subscription_keyboard

    progress = await render_progress(short=False)
    await _edit_message(callback,
        progress,
        parse_mode="HTML",
        reply_markup=subscription_keyboard()
    )
    await callback.answer()


# ============================================================
# ВНУТРЕННИЕ ФУНКЦИИ
# ============================================================

async def _handle_get_sub(callback: CallbackQuery):
    from config import MAX_USERS
    from database import count_active_users, is_limit_reached
    from keyboards import terms_keyboard, waitlist_keyboard

    user = await get_user(callback.from_user.id)

    if user and user["status"] == "active":
        await callback.answer("У тебя уже есть активная подписка", show_alert=True)
        return

    if user and user["status"] == "pending":
        await callback.answer("Заявка уже отправлена. Администратор проверит её.", show_alert=True)
        return

    if await is_limit_reached(MAX_USERS):
        if await is_in_waitlist(callback.from_user.id):
            position = await get_waitlist_position(callback.from_user.id)
            await _edit_message(callback,
                f"<b>Ты в листе ожидания</b>\n\n"
                f"Позиция: <b>{position}</b>.\n\n"
                f"Мы напишем, когда освободится место.",
                parse_mode="HTML",
                reply_markup=waitlist_keyboard()
            )
            await callback.answer()
            return

        active = await count_active_users()
        await _edit_message(callback,
            f"<b>Свободных мест нет</b>\n\n"
            f"Занято: {active} из {MAX_USERS}.\n\n"
            f"Можно встать в лист ожидания — мы напишем, когда появится место.",
            parse_mode="HTML",
            reply_markup=waitlist_keyboard()
        )
        await callback.answer()
        return

    await _edit_message(callback,
        "<b>Перед получением подписки</b>\n\n"
        "Ознакомься с документами:\n"
        "1. Правила использования\n"
        "2. Политика конфиденциальности\n"
        "3. Пользовательское соглашение\n\n"
        "Нажимая «Согласен с условиями», ты подтверждаешь, что прочитал их.",
        reply_markup=terms_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


async def _handle_my_sub(callback: CallbackQuery):
    from datetime import datetime
    from xui_client import XUIClient
    from keyboards import subscription_keyboard

    user = await get_user(callback.from_user.id)

    if not user or user["status"] != "active":
        await callback.answer("У тебя нет активной подписки", show_alert=True)
        return

    async with XUIClient() as xui:
        sub_url = xui.build_sub_url(user["sub_id"])
        client = await xui.get_client(user["xui_email"])

        expiry = client.get("expiryTime", 0)
        if expiry > 0:
            exp_dt = datetime.fromtimestamp(expiry / 1000)
            exp_date = exp_dt.strftime("%d.%m.%Y")
            remaining = (exp_dt - datetime.now()).total_seconds()
            days_left = (
                math.ceil(remaining / 86400)
                if remaining > 0
                else math.floor(remaining / 86400)
            )
            if days_left < 0:
                status_line = f"Истекла {exp_date}."
            elif days_left <= 3:
                status_line = f"Истекает {exp_date}. Осталось {days_left} дн."
            else:
                status_line = f"Активна до {exp_date}. Осталось {days_left} дн."
        else:
            status_line = "Бессрочная."

        traffic_up = client.get("up", 0) / (1024**3)
        traffic_down = client.get("down", 0) / (1024**3)

    await _edit_message(callback,
        f"<b>Твоя подписка</b>\n\n"
        f"Ссылка:\n<code>{sub_url}</code>\n\n"
        f"{status_line}\n"
        f"Лимит: 3 IP одновременно.\n"
        f"Трафик: получено {traffic_down:.2f} ГБ, отправлено {traffic_up:.2f} ГБ.",
        reply_markup=subscription_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


async def _handle_invite(callback: CallbackQuery):
    from keyboards import share_keyboard
    from config import BOT_USERNAME

    user = await get_user(callback.from_user.id)

    if not user:
        await callback.answer("Сначала получи подписку", show_alert=True)
        return

    invites = user["invites_count"] if user["invites_count"] else 0
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{callback.from_user.id}"

    await _edit_message(callback,
        f"<b>Приглашение друга</b>\n\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"Приглашено: {invites}.\n\n"
        f"Отправь ссылку другу. После регистрации он получит бесплатную подписку.",
        reply_markup=share_keyboard(BOT_USERNAME, callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()


async def _handle_invite_no_tg(callback: CallbackQuery):
    from keyboards import invite_contact_keyboard

    user = await get_user(callback.from_user.id)

    if not user or user["status"] != "active":
        await callback.answer("Сначала получи подписку", show_alert=True)
        return

    await callback.message.delete()
    await callback.message.answer(
        "<b>Гостевая подписка</b>\n\n"
        "Подписка работает без Telegram. Ссылку можно передать через WhatsApp, VK или SMS.\n\n"
        "Выбери друга из контактов или введи @username / ID. "
        "После этого я создам ссылку, которую можно передать любым способом.",
        reply_markup=invite_contact_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

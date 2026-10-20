"""Обработчики приглашения без Telegram.

Сценарий:
  A жмёт ➕ Добавить без TG
  → ReplyKeyboard с «👤 Выбрать из контактов»
  → A выбирает B из контактов
  → бот получает TG ID и username B
  → создаёт invite_link
  → возвращает главное меню
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS, BOT_NAME
from database import get_user, create_invite_link
from keyboards import (
    invite_share_keyboard,
    main_inline_menu,
)

router = Router()
logger = logging.getLogger(__name__)

# Ссылка на сайт (заменишь позже)
SITE_URL = "https://gb-skrepnet.duckdns.org:8443/invite"


@router.message(F.users_shared)
async def handle_shared_user(message: Message, state: FSMContext):
    """B выбран из контактов Telegram.
    Создаём invite-ссылку с friend_user_id и friend_username B."""
    shared = message.users_shared
    if not shared or not shared.users:
        await message.answer("❌ Никто не выбран")
        is_admin = message.from_user.id in ADMIN_IDS
        await message.answer(
            "📋 <b>Меню</b>",
            parse_mode="HTML",
            reply_markup=main_inline_menu(is_admin)
        )
        return

    friend = shared.users[0]
    friend_id = friend.user_id
    friend_username = friend.username
    friend_first_name = friend.first_name or ""

    # Нельзя пригласить себя
    if friend_id == message.from_user.id:
        await message.answer("❌ Нельзя пригласить самого себя")
        is_admin = message.from_user.id in ADMIN_IDS
        await message.answer(
            "📋 <b>Меню</b>",
            parse_mode="HTML",
            reply_markup=main_inline_menu(is_admin)
        )
        return

    # Проверяем, что B ещё не активен
    existing = await get_user(friend_id)
    if existing and existing["status"] == "active":
        display_name = f"@{friend_username}" if friend_username else friend_first_name or str(friend_id)
        await message.answer(
            f"⚠️ <b>{display_name} уже активен в {BOT_NAME}</b>"
        )
        is_admin = message.from_user.id in ADMIN_IDS
        await message.answer(
            "📋 <b>Меню</b>",
            parse_mode="HTML",
            reply_markup=main_inline_menu(is_admin)
        )
        return

    # Создаём invite-ссылку
    token = await create_invite_link(
        telegram_id=message.from_user.id,
        friend_user_id=friend_id,
        friend_username=friend_username,
    )

    invite_url = f"{SITE_URL}/{token}"

    display_name = f"@{friend_username}" if friend_username else friend_first_name or str(friend_id)

    await message.answer(
        f"✅ <b>Ссылка готова!</b>\n\n"
        f"👤 Пользователь: {display_name}\n"
        f"🆔 <code>{friend_id}</code>\n\n"
        f"🔗 <b>Ссылка:</b>\n"
        f"<code>{invite_url}</code>\n\n"
        f"📌 Отправь её пользователю.\n"
        f"⏳ Действует 7 дней, срабатывает 1 раз.",
        parse_mode="HTML",
        reply_markup=invite_share_keyboard(invite_url)
    )

    # Возвращаем главное меню
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        "📋 <b>Меню</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=main_inline_menu(is_admin)
    )

    await state.clear()


@router.message(F.text == "❌ Отмена")
async def invite_cancel_message(message: Message, state: FSMContext):
    """Отмена выбора контакта."""
    await state.clear()
    is_admin = message.from_user.id in ADMIN_IDS

    from keyboards import main_inline_menu
    from aiogram.types import ReplyKeyboardRemove
    await message.answer(
        "❌ Отменено.\n\n"
        "📋 <b>Меню</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=main_inline_menu(is_admin)
    )

@router.message(F.users_shared)
async def handle_users_shared_cancel(message: Message):
    """Срабатывает, если пользователь закрыл окно выбора контактов (нажал 'Отмена' в системном окне Telegram)."""
    shared = message.users_shared
    if not shared or not shared.users:
        # Пользователь ничего не выбрал (нажал отмену в окне Telegram)
        # Возвращаем клавиатуру
        from keyboards import invite_contact_keyboard
        await message.answer(
            "Выбор контакта отменён.\n\n"
            "Если передумал — нажми «❌ Отмена» ниже.",
            reply_markup=invite_contact_keyboard()
        )
        return

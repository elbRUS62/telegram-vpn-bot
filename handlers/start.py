import logging
import aiosqlite

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, CommandObject

from config import DB_PATH
from database import (
    get_user,
    find_pending_web_link_for_tg,
    increment_invites,
    add_invite,
)
from .utils import sanitize_email
from .menu import show_main_menu

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обычный /start (без deep-link): привязка по tg_id + главное меню."""
    from .web_link import bind_by_tg_id

    tg_id = message.from_user.id
    existing = await get_user(tg_id)
    if not existing:
        # B уже активировал веб-выдачу и зашёл в бота — привязываем
        link = await find_pending_web_link_for_tg(tg_id)
        if link:
            await bind_by_tg_id(message, link)
            return
    await show_main_menu(message)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject):
    """Обработка /start с deep-link:
       - ?start=ref_<id> — реферальная ссылка
       - ?start=link_<token> — привязка веб-пользователя
    """
    from .web_link import handle_web_link

    args = command.args or ""
    
    # ============================================================
    # Mini App — обработка действий (webapp_*)
    # ============================================================
    if args.startswith("webapp_"):
        action = args[7:]  # убираем "webapp_"
        user = await get_user(message.from_user.id)

        if action == "get_sub":
            if user and user["status"] == "active":
                await message.answer("У тебя уже есть активная подписка.")
                return
            if user and user["status"] == "pending":
                await message.answer("⏳ Заявка уже отправлена. Жди одобрения админа.")
                return
            from keyboards import terms_keyboard
            await message.answer(
                "📜 <b>Для получения подписки ознакомься с документами:</b>\n\n"
                "1. 📜 Правила использования\n"
                "2. 🔒 Политика конфиденциальности\n"
                "3. 📋 Пользовательское соглашение\n\n"
                "Нажимая «✅ Я согласен со всеми условиями», ты подтверждаешь, "
                "что ознакомился со всеми документами.",
                reply_markup=terms_keyboard(),
                parse_mode="HTML"
            )
            return

        if action == "invite_friend":
            if not user:
                await message.answer("Сначала получи подписку.")
                return
            from keyboards import share_keyboard
            from config import BOT_USERNAME
            invites = user["invites_count"] or 0
            ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
            await message.answer(
                f"👥 <b>Пригласи друга</b>\n\n"
                f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
                f"📊 Ты уже пригласил: {invites} чел.\n\n"
                f"💡 Отправь ссылку друзьям — они получат бесплатный VPN.",
                reply_markup=share_keyboard(BOT_USERNAME, message.from_user.id),
                parse_mode="HTML"
            )
            return

        if action == "invite_no_tg":
            if not user or user["status"] != "active":
                await message.answer("Сначала получи подписку.")
                return
            from keyboards import invite_contact_keyboard
            await message.answer(
                "➕ <b>Добавить пользователя без Telegram</b>\n\n"
                "Нажми «👤 Выбрать из контактов» — выбери человека из списка Telegram.\n"
                "Я получу его ID и username автоматически.\n\n"
                "⏳ После выбора создам одноразовую ссылку на 7 дней.",
                parse_mode="HTML",
                reply_markup=invite_contact_keyboard()
            )
            return

        if action == "donate":
            from keyboards import donate_keyboard
            from config import DONATE_TEXT, DONATE_URL
            await message.answer(
                f"{DONATE_TEXT}\n\n"
                f"Ссылка для доната: {DONATE_URL}",
                reply_markup=donate_keyboard()
            )
            return

        # Неизвестное действие — главное меню
        from .menu import show_main_menu
        await show_main_menu(message)
        return

    # Ветка 1: веб-привязка
    if args.startswith("link_"):
        token = args[5:]
        await handle_web_link(message, token)
        return

    # Ветка 2: реферальная (существующая логика)
    invited_by = None
    if args.startswith("ref_"):
        try:
            invited_by = int(args[4:])
        except ValueError:
            pass

    if invited_by == message.from_user.id:
        invited_by = None

    existing = await get_user(message.from_user.id)

    if existing is None and invited_by:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR REPLACE INTO users
                (telegram_id, username, first_name, xui_email, status, invited_by)
                VALUES (?, ?, ?, ?, 'new', ?)
            """, (
                message.from_user.id,
                message.from_user.username or "",
                message.from_user.first_name or "",
                sanitize_email(message.from_user.username, message.from_user.id),
                invited_by
            ))
            await db.commit()

        await increment_invites(invited_by)
        await add_invite(
            inviter_id=invited_by,
            invited_user_id=message.from_user.id,
            invited_username=message.from_user.username,
            invited_first_name=message.from_user.first_name,
            invite_type="ref"
        )

        try:
            await message.bot.send_message(
                invited_by,
                f"🎉 По твоей ссылке пришёл новый пользователь: "
                f"{message.from_user.full_name}!\n\n"
                f"Спасибо, что помогаешь проекту расти ❤️"
            )
        except Exception as e:
            logger.warning("Не удалось уведомить пригласившего {invited_by}: ")

    # Ветка 3: обычный deep-link (не ref, не link) — просто показать меню
    await show_main_menu(message)
    
    # ============================================================
    # Обработка действий из Mini App
    # ============================================================
    if args.startswith("webapp_"):
        action = args[7:]  # убираем "webapp_"
        user = await get_user(message.from_user.id)

        if action == "get_sub":
            if user and user["status"] == "active":
                await message.answer("У тебя уже есть активная подписка.")
                return
            from keyboards import terms_keyboard
            await message.answer(
                "📜 <b>Для получения подписки ознакомься с документами:</b>\n\n"
                "1. 📜 Правила использования\n"
                "2. 🔒 Политика конфиденциальности\n"
                "3. 📋 Пользовательское соглашение\n\n"
                "Нажимая «✅ Я согласен со всеми условиями», ты подтверждаешь, "
                "что ознакомился со всеми документами.",
                reply_markup=terms_keyboard(),
                parse_mode="HTML"
            )
            return

        if action == "invite_friend":
            if not user:
                await message.answer("Сначала получи подписку.")
                return
            from keyboards import share_keyboard
            from config import BOT_USERNAME
            invites = user["invites_count"] or 0
            ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
            await message.answer(
                f"👥 <b>Пригласи друга</b>\n\n"
                f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
                f"📊 Ты уже пригласил: {invites} чел.\n\n"
                f"💡 Отправь ссылку друзьям — они получат бесплатный VPN.",
                reply_markup=share_keyboard(BOT_USERNAME, message.from_user.id),
                parse_mode="HTML"
            )
            return

        if action == "invite_no_tg":
            if not user or user["status"] != "active":
                await message.answer("Сначала получи подписку.")
                return
            from keyboards import invite_contact_keyboard
            await message.answer(
                "➕ <b>Добавить пользователя без Telegram</b>\n\n"
                "Нажми «👤 Выбрать из контактов» — выбери человека из списка Telegram.\n\n"
                "⏳ После выбора создам одноразовую ссылку на 7 дней.",
                parse_mode="HTML",
                reply_markup=invite_contact_keyboard()
            )
            return

        if action == "donate":
            from keyboards import donate_keyboard
            from config import DONATE_TEXT, DONATE_URL
            await message.answer(
                f"{DONATE_TEXT}\n\n"
                f"Ссылка для доната: {DONATE_URL}",
                reply_markup=donate_keyboard()
            )
            return

        # Если неизвестное действие — просто показываем меню
        await show_main_menu(message)
        return
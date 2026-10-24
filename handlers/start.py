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


@router.message(CommandStart(deep_link=False))
async def cmd_start(message: Message):
    """Обычный /start без deep-link."""
    from .web_link import bind_by_tg_id

    tg_id = message.from_user.id
    existing = await get_user(tg_id)
    if not existing:
        link = await find_pending_web_link_for_tg(tg_id)
        if link:
            await bind_by_tg_id(message, link)
            return
    await show_main_menu(message, with_photo=True)

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
                await message.answer(
                    "Заявка уже отправлена. Администратор проверит её. "
                    "Статус можно посмотреть в приложении."
                )
                return
            from keyboards import terms_keyboard
            await message.answer(
                "<b>Перед получением подписки</b>\n\n"
                "Ознакомься с документами:\n"
                "1. Правила использования\n"
                "2. Политика конфиденциальности\n"
                "3. Пользовательское соглашение\n\n"
                "Нажимая «Согласен с условиями», ты подтверждаешь, что прочитал их.",
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
                f"<b>Приглашение друга</b>\n\n"
                f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
                f"Приглашено: {invites}.\n\n"
                f"Отправь ссылку другу. После регистрации он получит бесплатную подписку.",
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
                "<b>Гостевая подписка</b>\n\n"
                "Подписка работает без Telegram. Ссылку можно передать через WhatsApp, VK или SMS.\n\n"
                "1. Нажми «Выбрать из контактов».\n"
                "2. Выбери друга.\n"
                "3. Отправь ему ссылку.\n\n"
                "Если передумал, нажми «Отмена».",
                parse_mode="HTML",
                reply_markup=invite_contact_keyboard()
            )
            return

        if action == "donate":
            from keyboards import donate_keyboard
            from config import DONATE_TEXT, DONATE_URL
            from handlers.progress import access_warning
            text = DONATE_TEXT or "Поддержать проект"
            if DONATE_URL:
                text += f"\n\nСсылка для доната: {DONATE_URL}"
            warning = await access_warning()
            if warning:
                text += f"\n\n{warning}"
            await message.answer(text, reply_markup=donate_keyboard())
            return

        # Неизвестное действие — главное меню
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
                f"По твоей ссылке пришёл новый пользователь: "
                f"{message.from_user.full_name}.\n\n"
                f"Спасибо за помощь проекту."
            )
        except Exception:
            logger.warning("Не удалось уведомить пригласившего %s", invited_by, exc_info=True)

    # Ветка 3: обычный deep-link (не ref, не link) — просто показать меню
    await show_main_menu(message, with_photo=True)

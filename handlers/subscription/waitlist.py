from aiogram import F
from aiogram.types import CallbackQuery

from database import (
    add_to_waitlist,
    count_active_users,
    get_waitlist_position,
    is_in_waitlist,
    is_limit_reached,
)
from keyboards import waitlist_keyboard

from .common import logger, router

# ЛИСТ ОЖИДАНИЯ
# ============================================================

@router.callback_query(F.data == "join_waitlist")
async def join_waitlist_callback(callback: CallbackQuery):
    user = callback.from_user

    if await is_in_waitlist(user.id):
        position = await get_waitlist_position(user.id)
        await callback.answer(f"Ты уже в очереди, позиция: {position}", show_alert=True)
        return

    db_user = await get_user(user.id)
    if db_user and db_user["status"] == "active":
        await callback.answer("У тебя уже активная подписка", show_alert=True)
        return

    added = await add_to_waitlist(
        telegram_id=user.id,
        username=user.username or "",
        first_name=user.first_name or ""
    )

    if not added:
        await callback.answer("Ты уже в очереди", show_alert=True)
        return

    position = await get_waitlist_position(user.id)

    await callback.message.edit_text(
        f"<b>Ты в листе ожидания</b>\n\n"
        f"Твоя позиция: <b>{position}</b>\n\n"
        f"Мы напишем тебе, как только освободится место. "
        f"Обычно это занимает несколько дней.",
        parse_mode="HTML"
    )
    await callback.answer("Ты в очереди!")

    logger.info(f"{user.id} добавлен в лист ожидания (позиция {position})")

# ============================================================
# ОБРАБОТЧИК ДАННЫХ ОТ MINI APP
# ============================================================

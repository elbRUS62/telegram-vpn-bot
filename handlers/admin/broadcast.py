import asyncio

import aiosqlite
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import DB_PATH
from permissions import is_superadmin
from keyboards import admin_manage_keyboard
from ..states import AdminStates

from .common import router

# РАССЫЛКА
# ============================================================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправь текст сообщения, которое уйдёт всем активным пользователям.\n\n"
        "Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_broadcast_cancel")]
        ])
    )
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки."""
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(True),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.message(AdminStates.waiting_broadcast_text)
async def admin_broadcast_process(message: Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        return

    text = message.text.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT telegram_id FROM users WHERE status = 'active'") as cur:
            users = await cur.fetchall()

    data = await state.get_data()
    silent = data.get("broadcast_silent", False)

    sent = 0
    failed = 0
    for u in users:
        try:
            await message.bot.send_message(u["telegram_id"], text, disable_notification=silent)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ])
    )
    await state.clear()


# ============================================================

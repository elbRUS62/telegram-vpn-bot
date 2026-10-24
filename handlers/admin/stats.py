import aiosqlite
from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import BOT_NAME, DB_PATH, MAX_USERS
from permissions import is_admin_user
from database import (
    approve_user,
    count_users_by_statuses,
    delete_user,
    get_global_invites_stats,
    get_pending_requests,
    get_top_inviters,
    get_user,
    get_user_by_username,
    get_users_paginated,
    increment_renew_count,
    renew_user,
)
from .common import logger, router

# СТАТИСТИКА
# ============================================================

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
            total = (await cur.fetchone())["c"]

        async with db.execute("SELECT COUNT(*) as c FROM users WHERE status = 'active'") as cur:
            active = (await cur.fetchone())["c"]

        async with db.execute("SELECT COUNT(*) as c FROM users WHERE status = 'pending'") as cur:
            pending = (await cur.fetchone())["c"]

        async with db.execute(
            "SELECT COUNT(*) as c FROM users WHERE status = 'active' AND DATE(expires_at) <= DATE('now', '+3 days')"
        ) as cur:
            expiring = (await cur.fetchone())["c"]

        async with db.execute("SELECT COUNT(*) as c FROM waitlist") as cur:
            waitlist_count = (await cur.fetchone())["c"]

    invites_stats = await get_global_invites_stats()
    top_inviters = await get_top_inviters(5)

    free_slots = max(MAX_USERS - active, 0)

    text = (
        f"<b>Статистика {BOT_NAME}</b>\n\n"
        f"<b>Пользователи:</b>\n"
        f"• Всего: {total}\n"
        f"• Активных: {active}\n"
        f"• Ожидают одобрения: {pending}\n"
        f"• В листе ожидания: {waitlist_count}\n"
        f"• Свободно мест: {free_slots} из {MAX_USERS}\n"
        f"• Истекают через 3 дня: {expiring}\n\n"
        f"<b>Приглашения:</b>\n"
        f"• По реферальным: {invites_stats['ref']}\n"
        f"• Без Telegram: {invites_stats['no_tg']}\n"
        f"• Всего: {invites_stats['total']}\n\n"
    )

    if top_inviters:
        text += "<b>Топ-5 приглашающих:</b>\n"
        for i, inviter in enumerate(top_inviters, 1):
            user_data = await get_user(inviter["inviter_id"])
            if user_data and user_data["username"]:
                name = f"@{user_data['username']}"
            elif user_data and user_data["first_name"]:
                name = user_data["first_name"]
            else:
                name = f"ID {inviter['inviter_id']}"

            text += (
                f"{i}. {name}\n"
                f"   ├ реферальных: {inviter['ref_count']}\n"
                f"   ├ без TG: {inviter['no_tg_count']}\n"
                f"   └ всего: {inviter['total']}\n"
            )
    else:
        text += "Пока нет приглашений."

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="В главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


# ============================================================

# КОМАНДА /stats (на всякий случай)
# ============================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin_user(message.from_user.id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
            total = (await cur.fetchone())["c"]

        async with db.execute("SELECT COUNT(*) as c FROM users WHERE status = 'active'") as cur:
            active = (await cur.fetchone())["c"]

    await message.answer(
        f"Всего пользователей: {total}\nАктивных: {active}",
        parse_mode="HTML"
    )

import asyncio
import logging
from datetime import datetime, timedelta

import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from config import ADMIN_IDS, DB_PATH, DONATE_TEXT, MAX_USERS, BOT_NAME
from database import (
    get_user, get_user_by_username, is_admin, add_admin, remove_admin,
    get_all_admins, delete_user, renew_user, approve_user,
    get_global_invites_stats, get_top_inviters,
    get_pending_requests,
    get_users_paginated, count_users_by_statuses,
    increment_renew_count,
)
from xui_client import XUIClient
from keyboards import (
    admin_manage_keyboard,
    admin_panel_keyboard, email_conflict_keyboard, subscription_keyboard,
    users_list_keyboard, admin_submenu_users,
)
from .states import AdminStates
from .waitlist import notify_next_in_queue

router = Router()
logger = logging.getLogger(__name__)


# ============================================================
# СТАТИСТИКА
# ============================================================

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
        f"📊 <b>Статистика {BOT_NAME}</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {total}\n"
        f"• Активных: {active}\n"
        f"• Ожидают одобрения: {pending}\n"
        f"• В листе ожидания: {waitlist_count}\n"
        f"• Свободно мест: {free_slots} из {MAX_USERS}\n"
        f"• Истекают через 3 дня: {expiring}\n\n"
        f"📢 <b>Приглашения:</b>\n"
        f"• По реферальным: {invites_stats['ref']}\n"
        f"• Без Telegram: {invites_stats['no_tg']}\n"
        f"• Всего: {invites_stats['total']}\n\n"
    )

    if top_inviters:
        text += "🏆 <b>Топ-5 приглашающих:</b>\n"
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
        text += "🏆 Пока нет приглашений."

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


# ============================================================
# МЕНЮ УПРАВЛЕНИЯ
# ============================================================

@router.callback_query(F.data == "admin_manage")
async def admin_manage_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_manage_back")
async def admin_manage_back(callback: CallbackQuery):
    """Алиас для возврата в меню «Управление»."""
    await admin_manage_callback(callback)


@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.delete()
    await callback.answer()


# ============================================================
# РАССЫЛКА
# ============================================================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
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
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.message(AdminStates.waiting_broadcast_text)
async def admin_broadcast_process(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    text = message.text.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT telegram_id FROM users WHERE status = 'active'") as cur:
            users = await cur.fetchall()

    sent = 0
    failed = 0
    for u in users:
        try:
            await message.bot.send_message(u["telegram_id"], text, disable_notification=True)
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
# ПАНЕЛЬ 3x-ui
# ============================================================

@router.callback_query(F.data == "admin_panel")
async def admin_panel_link(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await callback.message.edit_text(
        "🔐 <b>Вход в панель 3x-ui</b>\n\n"
        "Нажми кнопку ниже — браузер откроет страницу входа.\n"
        "Пароль подставит менеджер паролей, если он у тебя есть.",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================================
# СПИСОК ЗАЯВОК
# ============================================================

@router.callback_query(F.data == "admin_list_requests")
async def admin_list_requests(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await _show_requests_list(callback)
    await callback.answer()


async def _show_requests_list(callback: CallbackQuery):
    requests = await get_pending_requests()

    if not requests:
        await callback.message.edit_text(
            "📋 <b>Заявок нет</b>\n\nВсе заявки обработаны.",
            parse_mode="HTML",
            reply_markup=admin_manage_keyboard()
        )
        return

    text = f"📋 <b>Заявки ({len(requests)})</b>\n\n"
    text += "Нажми на пользователя, чтобы открыть карточку:\n"

    buttons = []
    for req in requests:
        status_emoji = "⏳" if req["status"] == "pending" else "❌"
        name = req["first_name"] or "Без имени"
        short_name = name[:20] + "…" if len(name) > 20 else name
        label = f"{status_emoji} {short_name} — {req['telegram_id']}"

        buttons.append([InlineKeyboardButton(
            text=label[:64],
            callback_data=f"req_view:{req['telegram_id']}"
        )])

    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="admin_manage"
    )])

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("req_view:"))
async def request_view_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    status_ru = {
        "pending": "⏳ Ожидает одобрения",
        "rejected": "❌ Отклонена",
        "active": "✅ Активна",
        "new": "🆕 Новая",
    }.get(user["status"], user["status"])

    username = f"@{user['username']}" if user["username"] else "—"

    text = (
        f"👤 <b>{user['first_name'] or 'Без имени'}</b>\n\n"
        f"🆔 <code>{user['telegram_id']}</code>\n"
        f"📧 <code>{user['xui_email']}</code>\n"
        f"👤 {username}\n"
        f"📊 {status_ru}\n"
    )

    if user["created_at"]:
        text += f"📅 Создана: {user['created_at']}\n"

    buttons = []

    if user["status"] in ("pending", "rejected", "new"):
        buttons.append([
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"req_approve:{telegram_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"req_reject:{telegram_id}"
            ),
        ])

    buttons.append([InlineKeyboardButton(
        text="🗑 Удалить из БД",
        callback_data=f"req_delete:{telegram_id}"
    )])

    buttons.append([InlineKeyboardButton(
        text="⬅️ К списку",
        callback_data="admin_list_requests"
    )])

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("req_approve:"))
async def request_approve_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("⚠️ Уже активна", show_alert=True)
        return

    user_part = f"@{user['username']}" if user["username"] else str(telegram_id)
    auto_comment = f"{user_part} | bot"

    await state.update_data(approve_tg_id=telegram_id)

    await callback.message.edit_text(
        f"📝 <b>Комментарий для 3x-ui</b>\n\n"
        f"👤 {user['first_name']}\n"
        f"🆔 <code>{telegram_id}</code>\n\n"
        f"Введи текст (например, «VIP клиент, друг Ильи»)\n"
        f"или нажми «Пропустить» — тогда будет авто:\n"
        f"<code>{auto_comment}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏭ Пропустить",
                callback_data=f"req_skip_comment:{telegram_id}"
            )],
            [InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="admin_comment_cancel"
            )]
        ])
    )
    await state.set_state(AdminStates.waiting_comment)
    await callback.answer()


@router.callback_query(F.data == "admin_comment_cancel")
async def admin_comment_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода комментария."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("req_reject:"))
async def request_reject_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET status = 'rejected' WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

    await callback.answer("❌ Отклонено", show_alert=True)
    await _show_requests_list(callback)


@router.callback_query(F.data.startswith("req_delete:"))
async def request_delete_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    await delete_user(telegram_id)
    await callback.answer("🗑 Удалён", show_alert=True)

    await notify_next_in_queue(callback.bot)
    await _show_requests_list(callback)


# ============================================================
# СПИСКИ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

PER_PAGE = 10


@router.callback_query(F.data == "admin_extend")
async def admin_extend_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await _show_users_list(callback, action="extend", page=0)
    await callback.answer()


@router.callback_query(F.data == "admin_delete_user")
async def admin_delete_user_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await _show_users_list(callback, action="delete", page=0)
    await callback.answer()


@router.callback_query(F.data == "admin_reset")
async def admin_reset_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await _show_users_list(callback, action="reset", page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("users_page:"))
async def users_page_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    _, action, page_str = callback.data.split(":")
    await _show_users_list(callback, action=action, page=int(page_str))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


async def _show_users_list(callback: CallbackQuery, action: str, page: int):
    statuses_map = {
        "extend": ["active"],
        "delete": ["active", "pending", "rejected", "new"],
        "reset": ["active", "pending", "rejected", "new"],
    }
    statuses = statuses_map.get(action, ["active"])

    total = await count_users_by_statuses(statuses)
    users = await get_users_paginated(statuses, offset=0, limit=10000)

    def get_sort_name(u):
        if u["username"]:
            return u["username"].lower()
        if u["first_name"]:
            return u["first_name"].lower()
        return str(u["telegram_id"])

    def is_cyrillic(text: str) -> bool:
        for c in text:
            if 'а' <= c.lower() <= 'я' or c.lower() == 'ё':
                return True
        return False

    def sort_key(u):
        name = get_sort_name(u)
        cyr = is_cyrillic(name)
        return (0 if cyr else 1, name)

    users = sorted(users, key=sort_key)

    start = page * PER_PAGE
    end = start + PER_PAGE
    users = users[start:end]

    titles = {
        "extend": "🔄 Обновить подписку",
        "delete": "🗑 Удалить пользователя",
        "reset": "♻️ Сбросить заявку",
    }
    hints = {
        "extend": "Выбери пользователя, которому продлить подписку:",
        "delete": "Выбери пользователя, которого удалить (из БД и 3x-ui):",
        "reset": "Выбери пользователя для сброса заявки:",
    }

    if not users:
        await callback.message.edit_text(
            f"<b>{titles.get(action)}</b>\n\n"
            f"❌ Нет пользователей с подходящим статусом.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage")]
            ])
        )
        return

    text = (
        f"<b>{titles.get(action)}</b>\n\n"
        f"{hints.get(action)}\n\n"
        f"<i>Всего: {total}</i>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=users_list_keyboard(users, action, page, total, PER_PAGE)
    )


@router.callback_query(F.data.startswith("user_action:"))
async def user_action_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    _, action, tg_id_str = callback.data.split(":")
    telegram_id = int(tg_id_str)
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if action == "extend":
        await state.update_data(target_tg_id=telegram_id)
        await callback.message.edit_text(
            f"🔄 <b>Продление подписки</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"🆔 <code>{telegram_id}</code>\n"
            f"📧 {user['xui_email']}\n\n"
            f"На сколько <b>дней</b> продлить?\n\n"
            f"Введи число от 1 до 3650.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_extend_cancel")]
            ])
        )
        await state.set_state(AdminStates.waiting_extend_days)
        await callback.answer()
        return

    if action == "delete":
        try:
            async with XUIClient() as xui:
                try:
                    await xui.delete_client(user["xui_email"])
                except Exception:
                    pass
        except Exception as e:
            logger.error("Ошибка удаления из 3x-ui: ")

        await delete_user(telegram_id)
        await notify_next_in_queue(callback.bot)

        await callback.message.edit_text(
            f"🗑 <b>Пользователь удалён</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"🆔 <code>{telegram_id}</code>\n"
            f"📧 {user['xui_email']}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_delete_user")]
            ])
        )
        await callback.answer("Удалён")
        return

    if action == "reset":
        await delete_user(telegram_id)

        await callback.message.edit_text(
            f"♻️ <b>Заявка сброшена</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"🆔 <code>{telegram_id}</code>\n\n"
            f"Пользователь может подать заявку заново.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_reset")]
            ])
        )
        await callback.answer("Сброшено")
        return


@router.callback_query(F.data == "admin_extend_cancel")
async def admin_extend_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена продления подписки."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.message(AdminStates.waiting_extend_days)
async def admin_extend_days_process(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        days = int(message.text.strip())
        if days < 1 or days > 3650:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введи число от 1 до 3650.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_extend_cancel")]
            ])
        )
        return

    data = await state.get_data()
    telegram_id = data.get("target_tg_id")

    if not telegram_id:
        await message.answer(
            "❌ Ошибка: не найден пользователь",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )
        await state.clear()
        return

    user = await get_user(telegram_id)
    if not user:
        await message.answer(
            f"❌ Пользователь {telegram_id} не найден",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )
        await state.clear()
        return

    try:
        async with XUIClient() as xui:
            new_expiry = await xui.update_expiry(user["xui_email"], days=days)

            new_count = await increment_renew_count(telegram_id)
            date_str = new_expiry.strftime("%d.%m.%Y")

            user_part = f"@{user['username']}" if user["username"] else str(telegram_id)
            base_comment = f"{user_part} | бот"

            comment = f"{base_comment} | продлён ×{new_count} ({date_str})"

            try:
                await xui.update_comment(user["xui_email"], comment)
                logger.info(f"✅ Comment обновлён: {comment}")
            except Exception as e:
                logger.error("⚠️ Не удалось обновить comment: ")

        await renew_user(telegram_id, new_expires=new_expiry)

        await message.answer(
            f"✅ <b>Подписка продлена</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"📅 Новая дата: {new_expiry.strftime('%d.%m.%Y')}\n"
            f"⏱ +{days} дней",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
            ])
        )

        try:
            await message.bot.send_message(
                telegram_id,
                f"🎁 <b>Админ продлил твою подписку!</b>\n\n"
                f"📅 Новая дата: {new_expiry.strftime('%d.%m.%Y')}\n"
                f"⏱ +{days} дней",
                parse_mode="HTML"
            )
        except Exception:
            pass

        logger.info(f"✅ Продлено {user['xui_email']} на {days} дней")

    except Exception as e:
        logger.error("❌ Ошибка продления: ")
        await message.answer(
            f"❌ Ошибка",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )

    await state.clear()


# ============================================================
# ПОДМЕНЮ «ПОЛЬЗОВАТЕЛИ»
# ============================================================

@router.callback_query(F.data == "admin_menu_users")
async def admin_menu_users_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>\n\nВыбери действие:",
        reply_markup=admin_submenu_users(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================================
# СОЗДАНИЕ КЛИЕНТА С КОММЕНТАРИЕМ
# ============================================================

async def _do_approve(bot, chat_id: int, telegram_id: int, custom_comment: str = None):
    user = await get_user(telegram_id)
    if not user:
        await bot.send_message(chat_id, f"❌ Пользователь {telegram_id} не найден")
        return

    user_part = f"@{user['username']}" if user["username"] else str(telegram_id)

    if custom_comment:
        comment = f"{user_part} | {custom_comment}"
    else:
        comment = f"{user_part} | bot"

    try:
        async with XUIClient() as xui:
            try:
                sub_id = await xui.add_client(
                    user["xui_email"],
                    comment=comment,
                    tg_id=telegram_id,
                )
                await approve_user(telegram_id, sub_id)
                sub_url = xui.build_sub_url(sub_id)
            except Exception as e:
                if "email already in use" in str(e):
                    base_email = user["xui_email"]
                    await bot.send_message(
                        chat_id,
                        f"⚠️ <b>Email '{base_email}' уже занят в 3x-ui</b>\n\n"
                        f"👤 {user['first_name']}\n"
                        f"🆔 <code>{telegram_id}</code>\n\n"
                        f"Выбери новое имя для клиента:",
                        parse_mode="HTML",
                        reply_markup=email_conflict_keyboard(telegram_id, base_email)
                    )
                    return
                else:
                    raise

        await bot.send_message(
            chat_id,
            f"✅ <b>Заявка одобрена</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"📧 {user['xui_email']}\n"
            f"📝 <code>{comment}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_list_requests")]
            ])
        )

        await bot.send_message(
            telegram_id,
            f"🎉 <b>Твоя подписка готова!</b>\n\n"
            f"🔗 Ссылка:\n<code>{sub_url}</code>\n\n"
            f"📱 Лимит: 3 IP одновременно\n"
            f"⏳ Срок: 30 дней. Продлить можно через «🔑 Моя подписка».\n\n"
            f"{DONATE_TEXT}",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

        logger.info(f"✅ Одобрен {user['xui_email']} | comment={comment}")

    except Exception as e:
        logger.error(f"Ошибка при одобрении {user['xui_email']}")
        await bot.send_message(chat_id, "❌ Ошибка")


@router.message(AdminStates.waiting_comment)
async def comment_input_process(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    telegram_id = data.get("approve_tg_id")

    if not telegram_id:
        await message.answer(
            "❌ Ошибка: не найден пользователь",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )
        await state.clear()
        return

    custom_comment = message.text.strip()
    if not custom_comment:
        custom_comment = None

    await _do_approve(message.bot, message.chat.id, telegram_id, custom_comment)
    await state.clear()


@router.callback_query(F.data.startswith("req_skip_comment:"))
async def skip_comment_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await _do_approve(callback.bot, callback.message.chat.id, telegram_id, None)
    await state.clear()
    await callback.answer()


# ============================================================
# КОМАНДА /stats (на всякий случай)
# ============================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
            total = (await cur.fetchone())["c"]

        async with db.execute("SELECT COUNT(*) as c FROM users WHERE status = 'active'") as cur:
            active = (await cur.fetchone())["c"]

    await message.answer(
        f"📊 Всего: {total}\n✅ Активных: {active}",
        parse_mode="HTML"
    )
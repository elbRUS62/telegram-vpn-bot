from permissions import is_admin_user, is_superadmin
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


from database import (
    count_users_by_statuses,
    delete_user,
    get_user,
    get_users_paginated,
    increment_renew_count,
    renew_user,
)
from keyboards import admin_manage_keyboard, users_list_keyboard
from xui_client import XUIClient
from ..states import AdminStates
from ..waitlist import notify_next_in_queue

from .common import logger, router

# СПИСКИ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

PER_PAGE = 10


@router.callback_query(F.data == "admin_extend")
async def admin_extend_list(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        return
    await _show_users_list(callback, action="extend", page=0)
    await callback.answer()


@router.callback_query(F.data == "admin_delete_user")
async def admin_delete_user_list(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return
    await _show_users_list(callback, action="delete", page=0)
    await callback.answer()


@router.callback_query(F.data == "admin_reset")
async def admin_reset_list(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        return
    await _show_users_list(callback, action="reset", page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("users_page:"))
async def users_page_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
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
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    _, action, tg_id_str = callback.data.split(":")
    if action == "delete" and not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return
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
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(is_superadmin(callback.from_user.id)),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.message(AdminStates.waiting_extend_days)
async def admin_extend_days_process(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
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

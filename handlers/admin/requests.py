import aiosqlite
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import DB_PATH
from permissions import is_admin_user, is_superadmin
from database import (
    approve_user,
    delete_user,
    get_pending_requests,
    get_user,
    get_user_by_username,
    get_users_paginated,
    increment_renew_count,
    renew_user,
)
from keyboards import (
    admin_manage_keyboard,
    subscription_keyboard,
)
from xui_client import XUIClient
from ..states import AdminStates
from ..waitlist import notify_next_in_queue

from .common import logger, router

# СПИСОК ЗАЯВОК
# ============================================================

@router.callback_query(F.data == "admin_list_requests")
async def admin_list_requests(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        return
    await _show_requests_list(callback)
    await callback.answer()


async def _show_requests_list(callback: CallbackQuery):
    requests = await get_pending_requests()

    if not requests:
        await callback.message.edit_text(
            "<b>Заявок нет</b>\n\nВсе заявки обработаны.",
            parse_mode="HTML",
            reply_markup=admin_manage_keyboard(is_superadmin(callback.from_user.id))
        )
        return

    text = f"<b>Заявки ({len(requests)})</b>\n\n"
    text += "Нажми на пользователя, чтобы открыть карточку:\n"

    buttons = []
    for req in requests:
        name = req["first_name"] or "Без имени"
        short_name = name[:20] + "…" if len(name) > 20 else name
        label = f"{short_name} — {req['telegram_id']}"

        buttons.append([InlineKeyboardButton(
            text=label[:64],
            callback_data=f"req_view:{req['telegram_id']}"
        )])

    buttons.append([InlineKeyboardButton(
        text="Назад",
        callback_data="admin_manage"
    )])

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("req_view:"))
async def request_view_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    status_ru = {
        "pending": "Ожидает одобрения",
        "rejected": "Отклонена",
        "active": "Активна",
        "new": "Новая",
    }.get(user["status"], user["status"])

    username = f"@{user['username']}" if user["username"] else "—"

    text = (
        f"<b>{user['first_name'] or 'Без имени'}</b>\n\n"
        f"ID: <code>{user['telegram_id']}</code>\n"
        f"Email: <code>{user['xui_email']}</code>\n"
        f"Username: {username}\n"
        f"Статус: {status_ru}\n"
    )

    if user["created_at"]:
        text += f"Создана: {user['created_at']}\n"

    buttons = []

    if user["status"] in ("pending", "rejected", "new"):
        buttons.append([
            InlineKeyboardButton(
                text="Одобрить",
                callback_data=f"req_approve:{telegram_id}"
            ),
            InlineKeyboardButton(
                text="Отклонить",
                callback_data=f"req_reject:{telegram_id}"
            ),
        ])

    buttons.append([InlineKeyboardButton(
        text="Удалить из БД",
        callback_data=f"req_delete:{telegram_id}"
    )])

    buttons.append([InlineKeyboardButton(
        text="К списку",
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
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("Уже активна", show_alert=True)
        return

    await state.update_data(approve_tg_id=telegram_id)

    await callback.message.edit_text(
        f"<b>Комментарий для 3x-ui</b>\n\n"
        f"Пользователь: {user['first_name']}\n"
        f"ID: <code>{telegram_id}</code>\n\n"
        f"Введи комментарий или нажми «Пропустить» — поле останется пустым.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Пропустить",
                callback_data=f"req_skip_comment:{telegram_id}"
            )],
            [InlineKeyboardButton(
                text="Отмена",
                callback_data="admin_comment_cancel"
            )]
        ])
    )
    await state.set_state(AdminStates.waiting_comment)
    await callback.answer()


@router.callback_query(F.data == "admin_comment_cancel")
async def admin_comment_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода комментария."""
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "<b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(is_superadmin(callback.from_user.id)),
        parse_mode="HTML"
    )
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("req_reject:"))
async def request_reject_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET status = 'rejected' WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

    await callback.answer("Отклонено", show_alert=True)
    await _show_requests_list(callback)


@router.callback_query(F.data.startswith("req_delete:"))
async def request_delete_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    await delete_user(telegram_id)
    await callback.answer("Удалён", show_alert=True)

    await notify_next_in_queue(callback.bot)
    await _show_requests_list(callback)


# ============================================================

# СОЗДАНИЕ КЛИЕНТА С КОММЕНТАРИЕМ
# ============================================================

async def _do_approve(bot, chat_id: int, telegram_id: int, custom_comment: str = None):
    user = await get_user(telegram_id)
    if not user:
        await bot.send_message(chat_id, f"Пользователь {telegram_id} не найден")
        return

    comment = (custom_comment or "").strip()

    try:
        async with XUIClient() as xui:
            sub_id = await xui.get_or_create_client(
                user["xui_email"],
                comment=comment,
                tg_id=telegram_id,
            )
            await approve_user(telegram_id, sub_id)
            sub_url = xui.build_sub_url(sub_id)

        await bot.send_message(
            chat_id,
            f"<b>Заявка одобрена</b>\n\n"
            f"Пользователь: {user['first_name']}\n"
            f"Email: {user['xui_email']}\n"
            f"Комментарий: {comment or '—'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="К списку", callback_data="admin_list_requests")]
            ])
        )

        await bot.send_message(
            telegram_id,
            f"<b>Подписка активирована</b>\n\n"
            f"Ссылка:\n<code>{sub_url}</code>\n\n"
            f"Лимит: 3 IP одновременно.\n"
            f"Срок: 30 дней. Продлить можно в разделе «Моя подписка».\n\n"
            f"Поддержать проект можно в разделе «Донат».",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

        logger.info(f"Одобрен {user['xui_email']} | comment={comment}")

    except Exception as e:
        logger.error(f"Ошибка при одобрении {user['xui_email']}")
        await bot.send_message(
            chat_id,
            "Не удалось одобрить заявку. Проверь панель 3x-ui и повтори попытку."
        )


@router.message(AdminStates.waiting_comment)
async def comment_input_process(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        return

    data = await state.get_data()
    telegram_id = data.get("approve_tg_id")

    if not telegram_id:
        await message.answer(
            "Ошибка: не найден пользователь",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В управление", callback_data="admin_manage")]
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
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await _do_approve(callback.bot, callback.message.chat.id, telegram_id, None)
    await state.clear()
    await callback.answer()


# ============================================================

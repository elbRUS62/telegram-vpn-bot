from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import SUPPORT_USERNAME
from permissions import is_admin_user, get_admin_ids
from database import (
    approve_user,
    create_user_request,
    get_user,
    reject_user,
)
from keyboards import admin_approve_keyboard, subscription_keyboard
from xui_client import XUIClient
from ..states import AdminStates
from ..utils import sanitize_email

from .common import logger, router

# ЗАЯВКА НА ПОДПИСКУ
# ============================================================

@router.callback_query(F.data == "accept_terms")
async def accept_terms(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)

    if user and user["status"] == "active":
        await callback.answer("У тебя уже есть подписка", show_alert=True)
        return

    name = callback.from_user.username or callback.from_user.first_name or f"user{callback.from_user.id}"
    xui_email = sanitize_email(name, callback.from_user.id)

    invited_by = user["invited_by"] if user else None
    is_referral = invited_by is not None

    if user and user["status"] == "pending" and not is_referral:
        await callback.answer("Заявка уже отправлена", show_alert=True)
        return

    await create_user_request(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.first_name or "",
        xui_email,
        invited_by=invited_by
    )

    if is_referral:
        try:
            async with XUIClient() as xui:
                sub_id = await xui.get_or_create_client(
                    xui_email,
                    tg_id=callback.from_user.id,
                )
                await approve_user(callback.from_user.id, sub_id)
                sub_url = xui.build_sub_url(sub_id)

            logger.info(f"Реферал {xui_email} одобрен автоматически")

            await callback.message.edit_text(
                f"<b>Подписка активирована</b>\n\n"
                f"Ссылка:\n<code>{sub_url}</code>\n\n"
                f"Лимит: 3 IP одновременно.\n"
                f"Срок: 30 дней с момента активации.\n\n"
                f"Подключение: «Как подключиться». QR-код: «QR-код».\n"
                f"Поддержать проект можно в разделе «Донат».",
                reply_markup=subscription_keyboard(),
                parse_mode="HTML"
            )

            inviter = await get_user(invited_by)
            if inviter:
                inviter_username = f"@{inviter['username']}" if inviter["username"] else ""
                inviter_first = inviter["first_name"] or ""
                inviter_name = f"{inviter_username} ({inviter_first})" if inviter_username and inviter_first else inviter_username or inviter_first or str(invited_by)
            else:
                inviter_name = str(invited_by)

            for admin_id in get_admin_ids():
                try:
                    await callback.bot.send_message(
                        admin_id,
                        f"<b>Новый пользователь (реферал)</b>\n\n"
                        f"Пользователь: {callback.from_user.full_name}\n"
                        f"ID: <code>{callback.from_user.id}</code>\n"
                        f"Email: {xui_email}\n"
                        f"Пригласил: {inviter_name}",
                        parse_mode="HTML",
                        disable_notification=True
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error("Ошибка при создании реферала: ")
            await callback.message.edit_text(
                f"Ошибка. Обратись в поддержку: @{SUPPORT_USERNAME}"
            )

    else:
        for admin_id in get_admin_ids():
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"<b>Новая заявка</b>\n\n"
                    f"Пользователь: {callback.from_user.full_name}\n"
                    f"ID: <code>{callback.from_user.id}</code>\n"
                    f"Email: {xui_email}",
                    reply_markup=admin_approve_keyboard(callback.from_user.id),
                    parse_mode="HTML"
                )
            except Exception:
                logger.exception("Ошибка уведомления админу %s", admin_id)

        await callback.message.edit_text(
            "Заявка отправлена.\n\n"
            "Администратор проверит её. Обычно это занимает несколько минут. "
            "Статус можно посмотреть в приложении."
        )

    await callback.answer()


@router.callback_query(F.data == "decline_terms")
async def decline_terms(callback: CallbackQuery):
    await callback.message.edit_text(
        "Условия не приняты, подписка не выдана.\n\n"
        "Чтобы получить подписку, нажми «Получить подписку» и прими условия."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("approve:"))
async def approve_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("Заявка уже одобрена", show_alert=True)
        await callback.message.edit_text(
            f"Заявка уже одобрена\n\n"
            f"Пользователь: {user['first_name']}\n"
            f"Email: {user['xui_email']}"
        )
        return

    if user["status"] != "pending":
        await callback.answer(f"Неверный статус: {user['status']}", show_alert=True)
        return

    await state.update_data(approve_tg_id=telegram_id, from_notification=True)

    await callback.message.edit_text(
        f"<b>Комментарий для 3x-ui</b>\n\n"
        f"Пользователь: {user['first_name']}\n"
        f"ID: <code>{telegram_id}</code>\n\n"
        f"Введи комментарий или нажми «Пропустить» — поле останется пустым.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Пропустить",
                callback_data=f"approve_skip_comment:{telegram_id}"
            )],
            [InlineKeyboardButton(
                text="Отмена",
                callback_data="approve_comment_cancel"
            )]
        ])
    )
    await state.set_state(AdminStates.waiting_comment)
    await callback.answer()


@router.callback_query(F.data == "approve_comment_cancel")
async def approve_comment_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода комментария из уведомления о новой заявке."""
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "Одобрение отменено.\n\n"
        "Заявка осталась в статусе <b>pending</b>. Её можно одобрить позже "
        "через «Управление → Список заявок».",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="В управление", callback_data="admin_manage")]
        ])
    )
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("reject:"))
async def reject_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await reject_user(telegram_id)
    await callback.message.edit_text("Заявка отклонена")
    await callback.answer("Отклонено")


# ============================================================

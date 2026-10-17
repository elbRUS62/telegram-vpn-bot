import logging
import re
from datetime import datetime

import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS, DONATE_TEXT, DB_PATH, SUB_BASE_URL, SUB_PATH, MAX_USERS, BOT_NAME, SUPPORT_USERNAME
from database import (
    get_user, create_user_request, approve_user, renew_user,
    add_to_waitlist, is_in_waitlist, get_waitlist_position,
    count_active_users, is_limit_reached,
    increment_renew_count,
)
from xui_client import XUIClient
from keyboards import (
    admin_approve_keyboard, subscription_keyboard, donate_keyboard,
    email_conflict_keyboard, waitlist_keyboard,
)
from .utils import sanitize_email, make_qr_image
from .states import RegStates, AdminStates

router = Router()
logger = logging.getLogger(__name__)


# ============================================================
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
            user_part = f"@{callback.from_user.username}" if callback.from_user.username else str(callback.from_user.id)

            if invited_by:
                inviter = await get_user(invited_by)
                if inviter and inviter["username"]:
                    inviter_part = f"@{inviter['username']} ({invited_by})"
                else:
                    inviter_part = str(invited_by)
                auto_comment = f"{user_part} | реф от: {inviter_part}"
            else:
                auto_comment = f"{user_part} | bot"

            async with XUIClient() as xui:
                sub_id = await xui.add_client(
                    xui_email,
                    comment=auto_comment,
                    tg_id=callback.from_user.id,
                )
                await approve_user(callback.from_user.id, sub_id)
                sub_url = xui.build_sub_url(sub_id)

            logger.info(f"✅ Реферал {xui_email} одобрен автоматически")

            await callback.message.edit_text(
                f"🎉 <b>Твоя подписка готова!</b>\n\n"
                f"🔗 Ссылка:\n<code>{sub_url}</code>\n\n"
                f"📱 Лимит: 3 IP одновременно\n"
                f"⏳ Срок: 30 дней\n\n"
                f"📖 Как подключиться — жми «📖 Как подключиться»\n"
                f"📷 QR-код — жми «📷 QR-код»\n\n"
                f"{DONATE_TEXT}",
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

            for admin_id in ADMIN_IDS:
                try:
                    await callback.bot.send_message(
                        admin_id,
                        f"🆕 <b>Новый пользователь (реферал)</b>\n\n"
                        f"👤 {callback.from_user.full_name}\n"
                        f"🆔 <code>{callback.from_user.id}</code>\n"
                        f"📧 {xui_email}\n"
                        f"👥 Пригласил: {inviter_name}",
                        parse_mode="HTML",
                        disable_notification=True
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"❌ Ошибка при создании реферала: {e}")
            await callback.message.edit_text(
                f"❌ Ошибка. Обратись в поддержку: @{SUPPORT_USERNAME}"
            )

    else:
        for admin_id in ADMIN_IDS:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"🆕 <b>Новая заявка</b>\n\n"
                    f"👤 {callback.from_user.full_name}\n"
                    f"🆔 <code>{callback.from_user.id}</code>\n"
                    f"📧 {xui_email}",
                    reply_markup=admin_approve_keyboard(callback.from_user.id),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка уведомления админу {admin_id}: {e}")

        await callback.message.edit_text(
            "✅ Спасибо! Заявка отправлена.\n\n"
            "Жди одобрения админа — обычно это занимает несколько минут."
        )

    await callback.answer()


@router.callback_query(F.data == "decline_terms")
async def decline_terms(callback: CallbackQuery):
    await callback.message.edit_text(
        "❌ Ты не принял условия. Подписка не может быть выдана.\n\n"
        "Если передумаешь — нажми «📦 Получить подписку» снова."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("approve:"))
async def approve_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    user = await get_user(telegram_id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("⚠️ Заявка уже одобрена", show_alert=True)
        await callback.message.edit_text(
            f"⚠️ Заявка уже одобрена\n\n"
            f"Пользователь: {user['first_name']}\n"
            f"Email: {user['xui_email']}"
        )
        return

    if user["status"] != "pending":
        await callback.answer(f"Неверный статус: {user['status']}", show_alert=True)
        return

    user_part = f"@{user['username']}" if user["username"] else str(telegram_id)
    auto_comment = f"{user_part} | bot"

    await state.update_data(approve_tg_id=telegram_id, from_notification=True)

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
                callback_data=f"approve_skip_comment:{telegram_id}"
            )],
            [InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="approve_comment_cancel"
            )]
        ])
    )
    await state.set_state(AdminStates.waiting_comment)
    await callback.answer()


@router.callback_query(F.data == "approve_comment_cancel")
async def approve_comment_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода комментария из уведомления о новой заявке."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Одобрение отменено.\n\n"
        "Заявка осталась в статусе <b>pending</b> — можно одобрить позже через «🛠 Управление → 📋 Список заявок».",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
        ])
    )
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("reject:"))
async def reject_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await callback.message.edit_text("❌ Заявка отклонена")
    await callback.answer("Отклонено")


# ============================================================
# ПРОДЛЕНИЕ И QR
# ============================================================

@router.callback_query(F.data == "show_qr")
async def show_qr_callback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)

    if not user or user["status"] != "active":
        await callback.answer("Нет активной подписки", show_alert=True)
        return

    sub_url = f"{SUB_BASE_URL}{SUB_PATH}{user['sub_id']}"

    try:
        qr_file = make_qr_image(sub_url)

        # Удаляем старое сообщение с меню
        try:
            await callback.message.delete()
        except Exception:
            pass

        # Отправляем QR + только 2 кнопки
        await callback.message.answer_photo(
            photo=qr_file,
            caption="📷 <b>QR-код для быстрого подключения</b>\n\n"
                    "Открой Happ → «+» → «Сканировать QR»",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📖 Как подключиться",
                    callback_data="connect_help"
                )],
                [InlineKeyboardButton(
                    text="🏠 В главное меню",
                    callback_data="back_to_main"
                )],
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка QR: {e}")
        await callback.answer("Ошибка при создании QR", show_alert=True)


@router.callback_query(F.data == "renew")
async def renew_callback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)

    if not user or user["status"] != "active":
        await callback.answer("Нет активной подписки", show_alert=True)
        return

    try:
        async with XUIClient() as xui:
            new_expiry = await xui.update_expiry(user["xui_email"])

            new_count = await increment_renew_count(callback.from_user.id)
            date_str = new_expiry.strftime("%d.%m.%Y")

            user_part = f"@{user['username']}" if user["username"] else str(callback.from_user.id)
            base_comment = f"{user_part} | бот"

            comment = f"{base_comment} | продлён ×{new_count} ({date_str})"

            try:
                await xui.update_comment(user["xui_email"], comment)
                logger.info(f"✅ Comment обновлён: {comment}")
            except Exception as e:
                logger.error(f"⚠️ Не удалось обновить comment: {e}")

        await renew_user(callback.from_user.id, new_expires=new_expiry)
        exp_date = new_expiry.strftime("%d.%m.%Y")

        await callback.message.edit_text(
            f"✅ Подписка продлена!\n\n"
            f"📅 Новая дата окончания: {exp_date}\n"
            f"🔗 Ссылка та же.\n\n"
            f"{DONATE_TEXT}",
            reply_markup=donate_keyboard()
        )

    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ============================================================
# КОНФЛИКТ EMAIL
# ============================================================

@router.callback_query(F.data.startswith("retry_email:"))
async def retry_email_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    _, telegram_id_str, new_email = callback.data.split(":", 2)
    telegram_id = int(telegram_id_str)

    user = await get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("⚠️ Заявка уже одобрена", show_alert=True)
        return

    try:
        user_part = f"@{user['username']}" if user["username"] else str(telegram_id)
        auto_comment = f"{user_part} | bot (renamed)"

        async with XUIClient() as xui:
            sub_id = await xui.add_client(
                new_email,
                comment=auto_comment,
                tg_id=telegram_id,
            )
            await approve_user(telegram_id, sub_id)
            sub_url = xui.build_sub_url(sub_id)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET xui_email = ? WHERE telegram_id = ?",
                (new_email, telegram_id)
            )
            await db.commit()

        await callback.message.edit_text(
            f"✅ <b>Заявка одобрена</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"📧 {new_email}\n"
            f"🔗 subId: <code>{sub_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )

        await callback.bot.send_message(
            telegram_id,
            f"🎉 <b>Твоя подписка готова!</b>\n\n"
            f"🔗 Ссылка:\n<code>{sub_url}</code>\n\n"
            f"📱 Лимит: 3 IP одновременно\n"
            f"⏳ Срок: 30 дней. Продлить можно через «🔑 Моя подписка».\n\n"
            f"{DONATE_TEXT}",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

        logger.info(f"✅ Клиент {new_email} создан (subId={sub_id})")

    except Exception as e:
        logger.error(f"❌ Ошибка при создании {new_email}: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("manual_email:"))
async def manual_email_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    await state.update_data(conflict_tg_id=telegram_id)
    await callback.message.edit_text(
        f"✍️ <b>Введи новый email для клиента</b>\n\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n\n"
        f"Только латиница, цифры, <code>_</code> и <code>-</code>.\n"
        f"Например: <code>Ilya_new</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="manual_email_cancel")]
        ])
    )
    await state.set_state(AdminStates.waiting_custom_email)
    await callback.answer()


@router.callback_query(F.data == "manual_email_cancel")
async def manual_email_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена ручного ввода email."""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Ввод email отменён.\n\n"
        "Можешь попробовать снова через карточку заявки.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
        ])
    )
    await callback.answer("Отменено")


@router.message(AdminStates.waiting_custom_email)
async def manual_email_process(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    telegram_id = data.get("conflict_tg_id")

    if not telegram_id:
        await message.answer(
            "❌ Ошибка: не найден Telegram ID",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )
        await state.clear()
        return

    new_email = message.text.strip()

    if not re.match(r'^[a-zA-Z0-9_\-]{1,64}$', new_email):
        await message.answer(
            "❌ Неверный формат. Только латиница, цифры, <code>_</code> и <code>-</code>.\n\n"
            "Попробуй ещё раз или нажми «Отмена».",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="manual_email_cancel")]
            ])
        )
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
        user_part = f"@{user['username']}" if user["username"] else str(telegram_id)
        auto_comment = f"{user_part} | manual (admin)"

        async with XUIClient() as xui:
            sub_id = await xui.add_client(
                new_email,
                comment=auto_comment,
                tg_id=telegram_id,
            )
            await approve_user(telegram_id, sub_id)
            sub_url = xui.build_sub_url(sub_id)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET xui_email = ? WHERE telegram_id = ?",
                (new_email, telegram_id)
            )
            await db.commit()

        await message.answer(
            f"✅ <b>Клиент создан</b>\n\n"
            f"📧 {new_email}\n"
            f"🔗 subId: <code>{sub_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )

        await message.bot.send_message(
            telegram_id,
            f"🎉 <b>Твоя подписка готова!</b>\n\n"
            f"🔗 Ссылка:\n<code>{sub_url}</code>\n\n"
            f"📱 Лимит: 3 IP\n"
            f"⏳ Срок: 30 дней\n\n"
            f"{DONATE_TEXT}",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

        logger.info(f"✅ Клиент {new_email} создан вручную (subId={sub_id})")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


@router.callback_query(F.data.startswith("cancel_email:"))
async def cancel_email_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        f"❌ Заявка пользователя <code>{telegram_id}</code> отклонена (email занят).",
        parse_mode="HTML"
    )
    await callback.answer("Отклонено")


@router.callback_query(F.data.startswith("use_existing:"))
async def use_existing_email_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])

    user = await get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    if user["status"] == "active":
        await callback.answer("⚠️ Заявка уже одобрена", show_alert=True)
        return

    existing_email = user["xui_email"]

    try:
        async with XUIClient() as xui:
            client = await xui.get_client(existing_email)
            sub_id = client.get("subId")

            if not sub_id:
                raise Exception(f"У клиента {existing_email} нет subId — используй другое имя")

            # Обновляем tgId, чтобы фильтр в 3x-ui работал
            await xui.update_tg_id(existing_email, telegram_id)

            await approve_user(telegram_id, sub_id)
            sub_url = xui.build_sub_url(sub_id)

        await callback.message.edit_text(
            f"✅ <b>Использован существующий клиент</b>\n\n"
            f"👤 {user['first_name']}\n"
            f"📧 {existing_email}\n"
            f"🔗 subId: <code>{sub_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛠 В управление", callback_data="admin_manage")]
            ])
        )

        await callback.bot.send_message(
            telegram_id,
            f"🎉 <b>Твоя подписка готова!</b>\n\n"
            f"🔗 Ссылка:\n<code>{sub_url}</code>\n\n"
            f"📱 Лимит: 3 IP одновременно\n"
            f"⏳ Срок: 30 дней. Продлить можно через «🔑 Моя подписка».\n\n"
            f"{DONATE_TEXT}",
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

        logger.info(f"✅ Использован существующий клиент {existing_email} (subId={sub_id})")

    except Exception as e:
        logger.error(f"❌ Ошибка при использовании {existing_email}: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)

    await callback.answer()


# ============================================================
# ОДОБРЕНИЕ С КОММЕНТАРИЕМ (из уведомления)
# ============================================================

async def _do_approve_from_notification(bot, chat_id: int, telegram_id: int, custom_comment: str = None):
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
            parse_mode="HTML"
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

        logger.info(f"✅ Одобрен из уведомления {user['xui_email']} | comment={comment}")

    except Exception as e:
        logger.error(f"❌ Ошибка при одобрении {user['xui_email']}: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("approve_skip_comment:"))
async def approve_skip_comment_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await _do_approve_from_notification(callback.bot, callback.message.chat.id, telegram_id, None)
    await state.clear()
    await callback.answer()


# ============================================================
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
        f"✅ <b>Ты в листе ожидания</b>\n\n"
        f"📋 Твоя позиция: <b>{position}</b>\n\n"
        f"Мы напишем тебе, как только освободится место. "
        f"Обычно это занимает несколько дней.",
        parse_mode="HTML"
    )
    await callback.answer("Ты в очереди!")

    logger.info(f"✅ {user.id} добавлен в лист ожидания (позиция {position})")

# ============================================================
# ОБРАБОТЧИК ДАННЫХ ОТ MINI APP
# ============================================================

@router.message(F.web_app_data)
async def webapp_data_handler(message: Message):
    """Обработчик данных от Mini App (tg.sendData)."""
    import json

    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"web_app_data parse error: {e}")
        return

    action = data.get("action")
    logger.info(f"📱 Mini App action: {action} от {message.from_user.id}")

    # --- 📦 Получить подписку ---
    if action == "get_sub":
        from keyboards import terms_keyboard
        user = await get_user(message.from_user.id)

        if user and user["status"] == "active":
            await message.answer("У тебя уже есть активная подписка")
            return
        if user and user["status"] == "pending":
            await message.answer("⏳ Заявка уже отправлена. Жди одобрения админа.")
            return

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

    # --- 👥 Пригласить друга ---
    if action == "invite_friend":
        from keyboards import share_keyboard
        from config import BOT_USERNAME

        user = await get_user(message.from_user.id)
        if not user:
            await message.answer("Сначала получи подписку")
            return

        invites = user["invites_count"] if user["invites_count"] else 0
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

    # --- ➕ Добавить без TG ---
    if action == "invite_no_tg":
        from keyboards import invite_contact_keyboard

        user = await get_user(message.from_user.id)
        if not user or user["status"] != "active":
            await message.answer("Сначала получи подписку")
            return

        await message.answer(
            "➕ <b>Добавить пользователя без Telegram</b>\n\n"
            "Нажми «👤 Выбрать из контактов» — выбери человека из списка Telegram.\n"
            "Я получу его ID и username автоматически.\n\n"
            "⏳ После выбора создам одноразовую ссылку на 7 дней.",
            parse_mode="HTML",
            reply_markup=invite_contact_keyboard()
        )
        return

    # --- ❤️ Поддержать проект ---
    if action == "donate":
        from keyboards import donate_keyboard
        from config import DONATE_TEXT, DONATE_URL

        await message.answer(
            f"{DONATE_TEXT}\n\n"
            f"Ссылка для доната: {DONATE_URL}",
            reply_markup=donate_keyboard()
        )
        return

    # --- Неизвестное действие ---
    logger.warning(f"⚠️ Неизвестный action: {action}")
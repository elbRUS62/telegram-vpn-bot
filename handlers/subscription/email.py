import aiosqlite
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS, DB_PATH, DONATE_TEXT
from database import approve_user, get_user, reject_user
from keyboards import email_conflict_keyboard, subscription_keyboard
from xui_client import XUIClient
from ..states import AdminStates

from .common import logger, router

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

    except Exception:
        logger.exception("Ошибка при создании %s", new_email)
        await callback.answer("Ошибка", show_alert=True)

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
        await message.answer("❌ Ошибка")

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

    except Exception:
        logger.exception("Ошибка при использовании %s", existing_email)
        await callback.answer("Ошибка", show_alert=True)

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

        # Отправляем сообщение пользователю (с логированием ошибки)
        try:
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
            logger.info(f"✅ Сообщение отправлено пользователю {telegram_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение {telegram_id}: {e}")

        logger.info(f"✅ Одобрен из уведомления {user['xui_email']} | comment={comment}")

    except Exception as e:
        logger.error(f"Ошибка при одобрении {user['xui_email']}")
        await bot.send_message(chat_id, "❌ Ошибка")


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

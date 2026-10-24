from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import DONATE_TEXT
from database import approve_user, get_user
from keyboards import subscription_keyboard
from permissions import is_admin_user
from xui_client import XUIClient

from .common import logger, router


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
            sub_id = await xui.get_or_create_client(
                user["xui_email"],
                comment=comment,
                tg_id=telegram_id,
            )
            await approve_user(telegram_id, sub_id)
            sub_url = xui.build_sub_url(sub_id)

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

    except Exception:
        logger.exception("Ошибка при одобрении %s", user["xui_email"])
        await bot.send_message(chat_id, "❌ Ошибка")


@router.callback_query(F.data.startswith("approve_skip_comment:"))
async def approve_skip_comment_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    telegram_id = int(callback.data.split(":")[1])
    await _do_approve_from_notification(callback.bot, callback.message.chat.id, telegram_id, None)
    await state.clear()
    await callback.answer()

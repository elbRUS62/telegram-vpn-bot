from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import SUB_BASE_URL, SUB_PATH
from database import get_user, increment_renew_count, renew_user
from keyboards import donate_keyboard, subscription_keyboard
from xui_client import XUIClient
from ..utils import make_qr_image

from .common import logger, router

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
            caption="<b>QR-код для быстрого подключения</b>\n\n"
                    "Открой Happ → «+» → «Сканировать QR».",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Как подключиться",
                    callback_data="connect_help"
                )],
                [InlineKeyboardButton(
                    text="В главное меню",
                    callback_data="back_to_main"
                )],
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error("Ошибка QR: ")
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
                logger.info(f"Comment обновлён: {comment}")
            except Exception as e:
                logger.error("Не удалось обновить comment: ")

        await renew_user(callback.from_user.id, new_expires=new_expiry)
        exp_date = new_expiry.strftime("%d.%m.%Y")

        await callback.message.edit_text(
            f"<b>Подписка продлена</b>\n\n"
            f"Новая дата окончания: {exp_date}.\n"
            f"Ссылка не изменилась.\n\n"
            f"Поддержать проект можно в разделе «Донат».",
            reply_markup=donate_keyboard()
        )

    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)


# ============================================================

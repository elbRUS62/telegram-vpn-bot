import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery

from config import ADMIN_IDS, DONATE_TEXT, DONATE_URL, BOT_NAME
from keyboards import donate_keyboard, donate_stars_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "❤️ Поддержать проект")
async def donate(message: Message):
    await message.answer(
        f"{DONATE_TEXT}\n\n"
        f"Ссылка для доната: {DONATE_URL}",
        reply_markup=donate_keyboard()
    )


@router.callback_query(F.data == "donate_stars")
async def donate_stars_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "⭐ <b>Поддержать проект звёздами</b>\n\n"
        "Выбери сумму. Звёзды зачислятся мгновенно.\n\n"
        "1 ⭐ ≈ 1.5–2 ₽",
        reply_markup=donate_stars_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_donate")
async def back_to_donate(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{DONATE_TEXT}\n\n"
        f"Ссылка для доната: {DONATE_URL}",
        reply_markup=donate_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stars_"))
async def donate_stars_invoice(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    prices = [LabeledPrice(label=f"Поддержка {BOT_NAME}", amount=amount)]

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Поддержка {BOT_NAME}",
        description=f"Донат {amount} ⭐ на оплату сервера",
        payload=f"donate_{callback.from_user.id}_{amount}",
        provider_token="",
        currency="XTR",
        prices=prices
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    amount = payment.total_amount

    logger.info(f"⭐ Донат звёздами: {message.from_user.id} - {amount} ⭐")

    admin_text = (
        f"⭐ <b>Новый донат звёздами!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>От:</b> {message.from_user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"💵 <b>Сумма:</b> <code>{amount} ⭐</code>\n"
    )

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text,
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception:
            logger.exception("Ошибка отправки админу %s", admin_id)

    await message.answer(
        f"⭐ <b>Спасибо за поддержку!</b>\n\n"
        f"Ты отправил <code>{amount} ⭐</code>.\n"
        f"Это помогает серверу работать.\n\n"
        f"❤️ Ты лучший!",
        parse_mode="HTML"
    )
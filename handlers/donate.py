import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery

from config import DONATE_TEXT, DONATE_URL, BOT_NAME
from permissions import get_admin_ids
from keyboards import donate_keyboard, donate_stars_keyboard

router = Router()
logger = logging.getLogger(__name__)


def _donate_text() -> str:
    text = DONATE_TEXT or "Поддержать проект"
    if DONATE_URL:
        text += f"\n\nСсылка для доната: {DONATE_URL}"
    return text


@router.message(F.text == "Поддержать проект")
async def donate(message: Message):
    await message.answer(
        _donate_text(),
        reply_markup=donate_keyboard()
    )


@router.callback_query(F.data == "donate_stars")
async def donate_stars_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Поддержать проект звёздами</b>\n\n"
        "Выбери сумму. Звёзды зачислятся сразу.\n\n"
        "Ориентир: 1 звезда ≈ 1.5–2 ₽. Точная сумма будет показана перед оплатой.",
        reply_markup=donate_stars_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_donate")
async def back_to_donate(callback: CallbackQuery):
    await callback.message.edit_text(
        _donate_text(),
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
        description=f"Донат {amount} звёзд на оплату сервера.",
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

    logger.info(f"Донат звёздами: {message.from_user.id} - {amount} звёзд")

    admin_text = (
        f"<b>Новый донат звёздами</b>\n\n"
        f"От: {message.from_user.full_name}\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Сумма: <code>{amount} звёзд</code>"
    )

    for admin_id in get_admin_ids():
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
        f"<b>Спасибо за поддержку</b>\n\n"
        f"Отправлено: <code>{amount} звёзд</code>.\n"
        f"Средства идут на аренду сервера.",
        parse_mode="HTML"
    )

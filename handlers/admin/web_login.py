from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import WEB_BASE_URL
from permissions import is_admin_user
from web.utils.webadmin_auth import create_login_token

from .common import logger, router


@router.callback_query(F.data == "admin_web_login")
async def admin_web_login(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return

    if not WEB_BASE_URL:
        await callback.answer("Не настроен WEB_BASE_URL", show_alert=True)
        return

    try:
        token = create_login_token(callback.from_user.id)
    except Exception:
        logger.exception("Не удалось создать ссылку в веб-админку")
        await callback.answer("Не удалось создать ссылку", show_alert=True)
        return

    url = f"{WEB_BASE_URL}/admin/login?token={token}"
    await callback.message.answer(
        "Веб-админка SkrepNet\n\n"
        "Ссылка одноразовая и действует несколько минут. "
        "Открой её на компьютере или в браузере телефона.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть веб-админку", url=url)]
        ]),
    )
    await callback.answer("Ссылка создана")

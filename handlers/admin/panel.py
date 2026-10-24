from permissions import is_superadmin
from aiogram import F
from aiogram.types import CallbackQuery


from keyboards import admin_panel_keyboard

from .common import router

# ПАНЕЛЬ 3x-ui
# ============================================================

@router.callback_query(F.data == "admin_panel")
async def admin_panel_link(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    await callback.message.edit_text(
        "<b>Вход в панель 3x-ui</b>\n\n"
        "Нажми кнопку ниже — браузер откроет страницу входа.\n"
        "Пароль подставит менеджер паролей, если он у тебя есть.",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================================

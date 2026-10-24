from permissions import is_admin_user, is_superadmin
from aiogram import F
from aiogram.types import CallbackQuery


from keyboards import admin_manage_keyboard, admin_submenu_users

from .common import router

# МЕНЮ УПРАВЛЕНИЯ
# ============================================================

@router.callback_query(F.data == "admin_manage")
async def admin_manage_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Не твоя кнопка", show_alert=True)
        return
    await callback.message.edit_text(
        "🛠 <b>Управление ботом</b>\n\nВыбери действие:",
        reply_markup=admin_manage_keyboard(is_superadmin(callback.from_user.id)),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_manage_back")
async def admin_manage_back(callback: CallbackQuery):
    """Алиас для возврата в меню «Управление»."""
    await admin_manage_callback(callback)


@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        return
    await callback.message.delete()
    await callback.answer()


# ============================================================

# ПОДМЕНЮ «ПОЛЬЗОВАТЕЛИ»
# ============================================================

@router.callback_query(F.data == "admin_menu_users")
async def admin_menu_users_callback(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        return
    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>\n\nВыбери действие:",
        reply_markup=admin_submenu_users(is_superadmin(callback.from_user.id)),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================================

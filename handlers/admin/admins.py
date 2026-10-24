from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import get_user
from keyboards import admin_admins_keyboard, admin_admin_actions_keyboard, admin_manage_keyboard
from permissions import (
    deactivate_admin,
    is_superadmin,
    list_admins,
    save_admin,
    set_admin_role,
)
from ..states import AdminStates
from .common import logger, router


def _admin_label(admin: dict) -> str:
    name = admin.get("first_name") or admin.get("username") or str(admin["telegram_id"])
    username = f" @{admin['username']}" if admin.get("username") else ""
    role = "суперадмин" if admin.get("role") == "superadmin" else "админ"
    status = "" if admin.get("is_active", 1) else " · отключён"
    return f"{name}{username} — {role}{status}"


async def _render_admin_list(callback: CallbackQuery):
    admins = list_admins()
    await callback.message.edit_text(
        "🛡 <b>Администраторы</b>\n\n"
        "Суперадмин управляет доступами. Админ видит заявки, пользователей, "
        "тикеты и статистику, но не может менять других админов, делать рассылку "
        "и открывать панель 3x-ui.",
        parse_mode="HTML",
        reply_markup=admin_admins_keyboard(admins, callback.from_user.id),
    )


@router.callback_query(F.data == "admin_admins")
async def admin_admins_list(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    await _render_admin_list(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_admins_info:"))
async def admin_admin_info(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 1)[1])
    admin = next(
        (item for item in list_admins() if int(item["telegram_id"]) == telegram_id),
        None,
    )
    if not admin:
        await callback.answer("Админ не найден", show_alert=True)
        return

    await callback.message.edit_text(
        f"🛡 <b>Администратор</b>\n\n"
        f"{_admin_label(admin)}\n"
        f"<code>{telegram_id}</code>\n\n"
        f"Добавлен: {admin.get('added_at') or '—'}",
        parse_mode="HTML",
        reply_markup=admin_admin_actions_keyboard(admin, callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_admins_add")
async def admin_admins_add(callback: CallbackQuery, state: FSMContext):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_admin_id)
    await callback.message.edit_text(
        "➕ <b>Новый администратор</b>\n\n"
        "Отправь Telegram ID или @username пользователя. "
        "Он должен хотя бы раз открыть бота.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_admins")]
        ]),
    )
    await callback.answer()


@router.message(AdminStates.waiting_admin_id)
async def admin_admins_add_process(message: Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Отправь Telegram ID или @username.")
        return

    username = ""
    first_name = ""
    try:
        if raw.startswith("@"):
            chat = await message.bot.get_chat(raw)
            telegram_id = chat.id
            username = chat.username or ""
            first_name = chat.first_name or ""
        else:
            telegram_id = int(raw)

        user = await get_user(telegram_id)
        if user:
            username = user.get("username") or username
            first_name = user.get("first_name") or first_name

        save_admin(
            telegram_id,
            username=username,
            first_name=first_name,
            role="admin",
            added_by=message.from_user.id,
        )
    except (ValueError, TypeError):
        await message.answer(
            "Не удалось разобрать ID. Отправь число или @username.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_admins")]
            ]),
        )
        return
    except Exception:
        logger.exception("Не удалось добавить админа")
        await message.answer(
            "Не удалось добавить. Проверь ID и попробуй ещё раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_admins")]
            ]),
        )
        return

    await state.clear()

    try:
        await message.bot.send_message(
            telegram_id,
            "Ты назначен администратором SkrepNet.\n\n"
            "Тебе доступны админ-раздел в Mini App и админ-меню в боте.",
        )
    except Exception:
        logger.warning("Не удалось уведомить нового админа %s", telegram_id)

    await message.answer(
        f"✅ Админ добавлен: <code>{telegram_id}</code>",
        parse_mode="HTML",
        reply_markup=admin_admins_keyboard(list_admins(), message.from_user.id),
    )


@router.callback_query(F.data.startswith("admin_admins_promote:"))
@router.callback_query(F.data.startswith("admin_admins_demote:"))
async def admin_admins_role(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    action, raw_id = callback.data.split(":", 1)
    telegram_id = int(raw_id)
    role = "superadmin" if action.endswith("promote") else "admin"
    try:
        set_admin_role(telegram_id, role, actor_id=callback.from_user.id)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    role_label = (
        "суперадминистратором"
        if role == "superadmin"
        else "администратором"
    )
    try:
        await callback.bot.send_message(
            telegram_id,
            f"Твоя роль в SkrepNet изменена: {role_label}.\n\n"
            "Доступ к админ-разделу Mini App и админ-меню бота обновлён.",
        )
    except Exception:
        logger.warning("Не удалось уведомить админа %s", telegram_id)

    await callback.answer("Роль обновлена")
    await _render_admin_list(callback)


@router.callback_query(F.data.startswith("admin_admins_remove:"))
async def admin_admins_remove(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Доступно только суперадмину", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 1)[1])
    try:
        deactivate_admin(telegram_id, actor_id=callback.from_user.id)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    try:
        await callback.bot.send_message(
            telegram_id,
            "Твой доступ администратора SkrepNet отключён.",
        )
    except Exception:
        logger.warning("Не удалось уведомить админа %s", telegram_id)

    await callback.answer("Админ отключён")
    await _render_admin_list(callback)

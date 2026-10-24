from flask import jsonify, request

from config import BOT_TOKEN
from permissions import (
    deactivate_admin,
    list_admins,
    save_admin,
    set_admin_role,
)
from web.utils.async_helper import run_async
from web.utils.telegram import notify_user

from .common import _audit, admin_api, logger, superadmin_required


def _user_profile(user):
    """Приводит sqlite3.Row или dict к безопасному профилю."""
    if not user:
        return None
    data = dict(user)
    return {
        "username": data.get("username") or "",
        "first_name": data.get("first_name") or "",
    }


def _audit_async(admin_id, action, target_id=None, meta=""):
    run_async(_audit(admin_id, action, target_id, meta))


@admin_api.route("/admins", methods=["POST"])
@superadmin_required
def admins_list():
    return jsonify({"items": list_admins()})


@admin_api.route("/admins/add", methods=["POST"])
@superadmin_required
def admins_add():
    data = request.json or {}
    raw_id = data.get("tg_id")
    try:
        telegram_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Укажи Telegram ID числом"}), 400

    username = ""
    first_name = ""

    async def load_user():
        from database import get_user

        user = await get_user(telegram_id)
        profile = _user_profile(user)
        if profile:
            return profile

        # Если пользователь ещё не писал боту, getChat может не сработать.
        from telegram_api import call

        chat = await call(BOT_TOKEN, "getChat", chat_id=telegram_id)
        if not chat or chat.get("error"):
            return None
        return {
            "username": chat.get("username") or "",
            "first_name": chat.get("first_name") or "",
        }

    info = run_async(load_user())
    if isinstance(info, dict) and info.get("error"):
        return jsonify(info), 400
    if info:
        username = info.get("username", "")
        first_name = info.get("first_name", "")

    try:
        role = save_admin(
            telegram_id,
            username=username,
            first_name=first_name,
            role=data.get("role") or "admin",
            added_by=request.admin_user["id"],
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    _audit_async(
        request.admin_user["id"],
        "admin_add",
        telegram_id,
        f"role={role}",
    )
    role_label = (
        "суперадминистратором"
        if role == "superadmin"
        else "администратором"
    )
    notify_user(
        telegram_id,
        f"Ты назначен {role_label} SkrepNet.\n\n"
        "Тебе доступны админ-раздел в Mini App и админ-меню в боте.",
    )
    return jsonify({"success": True, "role": role})


@admin_api.route("/admins/role", methods=["POST"])
@superadmin_required
def admins_role():
    data = request.json or {}
    try:
        telegram_id = int(data.get("tg_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Укажи Telegram ID числом"}), 400
    role = data.get("role")

    try:
        role = set_admin_role(
            telegram_id,
            role,
            actor_id=request.admin_user["id"],
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    _audit_async(
        request.admin_user["id"],
        "admin_role",
        telegram_id,
        f"role={role}",
    )
    role_label = (
        "суперадминистратором"
        if role == "superadmin"
        else "администратором"
    )
    notify_user(
        telegram_id,
        f"Твоя роль в SkrepNet изменена: {role_label}.\n\n"
        "Доступ к админ-разделу Mini App и админ-меню бота обновлён.",
    )
    return jsonify({"success": True, "role": role})


@admin_api.route("/admins/remove", methods=["POST"])
@superadmin_required
def admins_remove():
    data = request.json or {}
    try:
        telegram_id = int(data.get("tg_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Укажи Telegram ID числом"}), 400

    try:
        deactivate_admin(telegram_id, actor_id=request.admin_user["id"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    _audit_async(
        request.admin_user["id"],
        "admin_remove",
        telegram_id,
    )
    notify_user(
        telegram_id,
        "Твой доступ администратора SkrepNet отключён.",
    )
    return jsonify({"success": True})

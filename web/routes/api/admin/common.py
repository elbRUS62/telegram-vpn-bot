import hmac
import logging
import sqlite3
from functools import wraps

import aiosqlite
from flask import Blueprint, jsonify, request, session

from config import DB_PATH
from permissions import get_admin_role, is_admin_user, is_superadmin
from web.utils.auth import validate_init_data

logger = logging.getLogger(__name__)

admin_api = Blueprint("miniapp_admin_api", __name__, url_prefix="/api/miniapp/admin")
VALID_DAYS = {1, 3, 7, 14, 30, 90, 180, 365, 3650}


def _session_authenticate():
    telegram_id = session.get("admin_id")
    if not telegram_id:
        return None

    role = get_admin_role(telegram_id)
    if not role:
        session.clear()
        return None, None, (jsonify({"error": "Сессия истекла"}), 401)

    if request.method != "GET":
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            return None, None, (jsonify({"error": "Неверный CSRF-токен"}), 403)

    user = {"id": telegram_id, "first_name": "", "username": ""}
    try:
        connection = sqlite3.connect(DB_PATH, timeout=5)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT first_name, username FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        connection.close()
        if row:
            user["first_name"] = row["first_name"] or ""
            user["username"] = row["username"] or ""
    except Exception:
        logger.warning("web admin: не удалось прочитать профиль %s", telegram_id)

    return user, role, None


def _authenticate():
    data = request.json or {}
    if data.get("init_data"):
        user = validate_init_data(data.get("init_data", ""))
        if not user:
            return None, None, (jsonify({"error": "Неверная авторизация"}), 401)

        telegram_id = user.get("id")
        if not is_admin_user(telegram_id):
            return None, None, (jsonify({"error": "Доступ запрещён"}), 403)

        return user, get_admin_role(telegram_id), None

    if session.get("admin_id"):
        return _session_authenticate()

    return None, None, (jsonify({"error": "Неверная авторизация"}), 401)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user, role, error = _authenticate()
        if error:
            return error
        request.admin_user = user
        request.admin_role = role
        return fn(*a, **kw)

    return wrapper


def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user, role, error = _authenticate()
        if error:
            return error
        if not is_superadmin(user.get("id")):
            return jsonify({"error": "Доступно только суперадмину"}), 403
        request.admin_user = user
        request.admin_role = role
        return fn(*a, **kw)

    return wrapper


async def _audit(admin_id, action, target_id=None, meta=""):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO admin_audit(admin_id, action, target_id, meta) VALUES(?,?,?,?)",
                (admin_id, action, target_id, meta),
            )
            await db.commit()
    except Exception as e:
        logger.warning("audit insert failed: %s", e)

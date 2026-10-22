import logging
from functools import wraps

import aiosqlite
from flask import Blueprint, jsonify, request

from config import ADMIN_IDS, DB_PATH
from web.utils.auth import validate_init_data

logger = logging.getLogger(__name__)

admin_api = Blueprint("miniapp_admin_api", __name__, url_prefix="/api/miniapp/admin")
VALID_DAYS = {1, 3, 7, 14, 30, 90, 180, 365, 3650}

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        data = request.json or {}
        user = validate_init_data(data.get("init_data", ""))
        if not user:
            return jsonify({"error": "Неверная авторизация"}), 401
        if user.get("id") not in ADMIN_IDS:
            return jsonify({"error": "Доступ запрещён"}), 403
        request.admin_user = user
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

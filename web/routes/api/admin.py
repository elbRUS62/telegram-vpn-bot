"""API-роуты админки Mini App. Все методы POST, init_data в теле."""
import logging
from functools import wraps

import aiosqlite
from flask import Blueprint, jsonify, request

from config import ADMIN_IDS, DB_PATH, MAX_USERS, BOT_NAME
from web.utils.auth import validate_init_data
from web.utils.async_helper import run_async

logger = logging.getLogger(__name__)

admin_api = Blueprint("miniapp_admin_api", __name__, url_prefix="/api/miniapp/admin")

VALID_DAYS = {1, 3, 7, 14, 30, 90, 180, 365, 3650}


# ---------------- auth ----------------

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


# ---------------- stats ----------------

@admin_api.route("/stats", methods=["POST"])
@admin_required
def stats():
    async def get_data():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            async def one(sql, *args):
                async with db.execute(sql, args) as cur:
                    r = await cur.fetchone()
                    return r[0] if r else 0

            total    = await one("SELECT COUNT(*) FROM users")
            active   = await one("SELECT COUNT(*) FROM users WHERE status='active'")
            pending  = await one("SELECT COUNT(*) FROM users WHERE status='pending'")
            rejected = await one("SELECT COUNT(*) FROM users WHERE status='rejected'")
            expiring = await one(
                "SELECT COUNT(*) FROM users WHERE status='active' "
                "AND DATE(expires_at) BETWEEN DATE('now') AND DATE('now','+3 days')"
            )
            waitlist = await one("SELECT COUNT(*) FROM waitlist")
            donated  = await one(
                "SELECT COALESCE(SUM(amount),0) FROM donations WHERE currency='RUB'"
            )
            invites  = await one("SELECT COUNT(*) FROM invites")

        return {
            "users_total": total,
            "active": active,
            "pending": pending,
            "rejected": rejected,
            "expiring_3d": expiring,
            "waitlist": waitlist,
            "donated_rub": int(round(donated or 0)),
            "invites_total": invites,
            "max_users": MAX_USERS,
            "free_slots": max(MAX_USERS - active, 0),
            "bot_name": BOT_NAME,
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception as e:
        logger.exception("admin/stats failed")
        return jsonify({"error": str(e)}), 500


# ---------------- users ----------------

@admin_api.route("/users", methods=["POST"])
@admin_required
def users_list():
    data   = request.json or {}
    q      = (data.get("q") or "").strip().lower()
    status = data.get("status") or "all"
    page   = max(1, int(data.get("page", 1)))
    limit  = min(50, max(1, int(data.get("limit", 20))))
    offset = (page - 1) * limit

    async def get_data():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            where, args = [], []
            if status != "all":
                where.append("status=?")
                args.append(status)
            if q:
                where.append(
                    "(LOWER(COALESCE(username,'')) LIKE ? "
                    "OR LOWER(COALESCE(first_name,'')) LIKE ? "
                    "OR CAST(telegram_id AS TEXT) LIKE ?)"
                )
                like = f"%{q}%"
                args += [like, like, like]
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""

            async with db.execute(f"SELECT COUNT(*) FROM users {where_sql}", args) as cur:
                total = (await cur.fetchone())[0]

            async with db.execute(
                f"""SELECT telegram_id, username, first_name, status, xui_email,
                           expires_at, invites_count, renew_count, created_at
                    FROM users {where_sql}
                    ORDER BY (status='pending') DESC, created_at DESC
                    LIMIT ? OFFSET ?""",
                (*args, limit, offset),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

        return {
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": offset + len(rows) < total,
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception as e:
        logger.exception("admin/users failed")
        return jsonify({"error": str(e)}), 500


@admin_api.route("/user", methods=["POST"])
@admin_required
def user_card():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def get_data():
        from database import get_user
        u = await get_user(tg_id)
        if not u:
            return {"error": "Пользователь не найден"}
        return {"user": dict(u)}

    r = run_async(get_data())
    if "error" in r:
        return jsonify(r), 404
    return jsonify(r)


# ---------------- requests (pending) ----------------

@admin_api.route("/requests", methods=["POST"])
@admin_required
def requests_list():
    async def get_data():
        from database import get_pending_requests
        rows = await get_pending_requests()
        return {"items": [dict(r) for r in rows], "total": len(rows)}

    try:
        return jsonify(run_async(get_data()))
    except Exception as e:
        logger.exception("admin/requests failed")
        return jsonify({"error": str(e)}), 500


# ---------------- actions ----------------

@admin_api.route("/reject", methods=["POST"])
@admin_required
def reject():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def do():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET status='rejected' WHERE telegram_id=?", (tg_id,))
            await db.commit()
        await _audit(request.admin_user["id"], "reject", tg_id)
        return {"success": True}

    try:
        return jsonify(run_async(do()))
    except Exception as e:
        logger.exception("admin/reject failed")
        return jsonify({"error": str(e)}), 500


@admin_api.route("/extend", methods=["POST"])
@admin_required
def extend():
    data  = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    days  = int(data.get("days", 0))
    if days not in VALID_DAYS:
        return jsonify({"error": "Недопустимое количество дней"}), 400

    async def do():
        from database import get_user, renew_user, increment_renew_count
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if not user:
            return {"error": "Пользователь не найден"}
        if not user.get("xui_email"):
            return {"error": "У пользователя нет xui_email"}

        async with XUIClient() as xui:
            new_expiry = await xui.update_expiry(user["xui_email"], days=days)
            try:
                new_count = await increment_renew_count(tg_id)
                user_part = f"@{user['username']}" if user.get("username") else str(tg_id)
                date_str  = new_expiry.strftime("%d.%m.%Y")
                await xui.update_comment(
                    user["xui_email"],
                    f"{user_part} | бот | продлён ×{new_count} ({date_str})",
                )
            except Exception as e:
                logger.warning("comment update failed for %s: %s", user["xui_email"], e)

        await renew_user(tg_id, new_expires=new_expiry)
        await _audit(request.admin_user["id"], "extend", tg_id, f"days={days}")

        return {
            "success": True,
            "new_expires_at": new_expiry.strftime("%d.%m.%Y"),
            "days_added": days,
        }

    try:
        r = run_async(do())
    except Exception as e:
        logger.exception("admin/extend failed")
        return jsonify({"error": str(e)}), 500
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


@admin_api.route("/delete", methods=["POST"])
@admin_required
def delete():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def do():
        from database import get_user, delete_user
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if user and user.get("xui_email"):
            try:
                async with XUIClient() as xui:
                    await xui.delete_client(user["xui_email"])
            except Exception as e:
                logger.warning("xui delete failed for %s: %s", user["xui_email"], e)
        await delete_user(tg_id)
        await _audit(request.admin_user["id"], "delete", tg_id)
        return {"success": True}

    try:
        return jsonify(run_async(do()))
    except Exception as e:
        logger.exception("admin/delete failed")
        return jsonify({"error": str(e)}), 500

import aiosqlite
from flask import jsonify, request

from config import DB_PATH
from web.utils.async_helper import run_async

from .common import admin_api, superadmin_required

@admin_api.route("/audit", methods=["POST"])
@superadmin_required
def audit_log():
    """Возвращает журнал действий админов."""
    data = request.json or {}
    limit = min(200, max(1, int(data.get("limit", 50))))
    offset = max(0, int(data.get("offset", 0)))
    action_filter = data.get("action")
    target_filter = data.get("target_id")

    async def do():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            conditions = []
            args = []
            if action_filter:
                conditions.append("a.action = ?")
                args.append(action_filter)
            if target_filter:
                conditions.append("a.target_id = ?")
                args.append(int(target_filter))
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            async with db.execute(f"""
                SELECT a.id, a.admin_id, a.action, a.target_id, a.meta, a.created_at,
                       u_admin.username as admin_username, u_admin.first_name as admin_first_name,
                       u_target.username as target_username, u_target.first_name as target_first_name
                FROM admin_audit a
                LEFT JOIN users u_admin ON u_admin.telegram_id = a.admin_id
                LEFT JOIN users u_target ON u_target.telegram_id = a.target_id
                {where}
                ORDER BY a.id DESC
                LIMIT ? OFFSET ?
            """, (*args, limit, offset)) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

            async with db.execute(f"SELECT COUNT(*) FROM admin_audit a {where}", args) as cur:
                total = (await cur.fetchone())[0]

            # Если передан target_id — дополнительно тянем приглашения этого юзера
            invites = []
            if target_filter:
                async with db.execute("""
                    SELECT i.id, i.invited_user_id, i.invited_username, i.invited_first_name,
                           i.type, i.created_at,
                           u.first_name AS invited_first_name_full, u.username AS invited_username_full
                    FROM invites i
                    LEFT JOIN users u ON u.telegram_id = i.invited_user_id
                    WHERE i.inviter_id = ?
                    ORDER BY i.id DESC
                """, (int(target_filter),)) as cur:
                    invites = [dict(r) for r in await cur.fetchall()]

        return {
            "items": rows,
            "invites": invites,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    try:
        return jsonify(run_async(do()))
    except Exception as e:
        logger.error("admin/audit failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

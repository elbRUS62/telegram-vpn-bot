import aiosqlite
from flask import jsonify, request

from config import BOT_NAME, DB_PATH, MAX_USERS, XUI_PANELS
from web.utils.async_helper import run_async

from .common import admin_api, admin_required, logger

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
            blocked  = await one("SELECT COUNT(*) FROM users WHERE status='blocked'")
            expiring = await one(
                "SELECT COUNT(*) FROM users WHERE status='active' "
                "AND DATE(expires_at) BETWEEN DATE('now') AND DATE('now','+3 days')"
            )
            waitlist = await one("SELECT COUNT(*) FROM waitlist")
            donated  = await one(
                "SELECT COALESCE(SUM(amount),0) FROM donations WHERE currency='RUB'"
            )
            invites  = await one("SELECT COUNT(*) FROM invites")
            tickets_open = await one(
                "SELECT COUNT(*) FROM support_tickets "
                "WHERE status IN ('open','answered')"
            )
            tickets_unread = await one(
                "SELECT COUNT(*) FROM support_tickets "
                "WHERE status != 'closed' AND unread_admin = 1"
            )

            # --- Трафик (накопительный, из 3x-ui) ---
            traffic_gb = None
            try:
                from xui_client import XUIClient
                from asyncio import gather

                async with db.execute(
                    "SELECT xui_email FROM users WHERE status='active' "
                    "AND xui_email IS NOT NULL AND xui_email != ''"
                ) as cur2:
                    emails = [row[0] for row in await cur2.fetchall()]

                if emails:
                    async with XUIClient() as xui:
                        results = await gather(
                            *[xui.get_client_traffic(e) for e in emails],
                            return_exceptions=True,
                        )
                        traffic_total = 0
                        for r in results:
                            if isinstance(r, dict):
                                traffic_total += r.get("up", 0) + r.get("down", 0)
                        traffic_gb = round(traffic_total / (1024 ** 3), 1)
                else:
                    traffic_gb = 0
            except Exception:
                logger.error("admin/stats: traffic failed")
                traffic_gb = None

            # --- Онлайн-подсчёт (VPN) по всем панелям 3x-ui ---
            # Используем /panel/api/clients/onlines — именно этот список
            # показывает панель 3x-ui как «В сети».
            online_count = 0
            from xui_client import XUIClient
            for panel in XUI_PANELS:
                try:
                    async with XUIClient(panel) as xui:
                        res = await xui._post("/panel/api/clients/onlines", {})
                        if res.get("success"):
                            online_count += len(res.get("obj", []) or [])
                except Exception:
                    logger.error(
                        "admin/stats: online_count failed for panel %s",
                        panel.get("id"),
                    )

        return {
            "users_total": total,
            "active": active,
            "pending": pending,
            "rejected": rejected,
            "blocked": blocked,
            "expiring_3d": expiring,
            "waitlist": waitlist,
            "donated_rub": int(round(donated or 0)),
            "invites_total": invites,
            "traffic_gb": traffic_gb,
            "max_users": MAX_USERS,
            "active_slots": active,            # Занято
            "free_slots": max(MAX_USERS - active, 0),
            "bot_name": BOT_NAME,
            "online_count": online_count,
            "tickets_open": tickets_open,
            "tickets_unread": tickets_unread,
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception as e:
        logger.error("admin/stats failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

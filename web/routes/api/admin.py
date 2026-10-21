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
                logger.exception("admin/stats: traffic failed")
                traffic_gb = None

            # --- Онлайн-подсчёт (VPN) из 3x-ui ---
            # Используем /panel/api/clients/onlines — именно этот список
            # показывает панель 3x-ui как «В сети».
            online_count = 0
            try:
                from xui_client import XUIClient
                async with XUIClient() as xui:
                    res = await xui._post("/panel/api/clients/onlines", {})
                    if res.get("success"):
                        online_count = len(res.get("obj", []) or [])
            except Exception:
                logger.exception("admin/stats: online_count failed")
                online_count = 0

        return {
            "users_total": total,
            "active": active,
            "pending": pending,
            "rejected": rejected,
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
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception as e:
        logger.error("admin/stats failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# ---------------- users ----------------

@admin_api.route("/sync", methods=["POST"])
@admin_required
def sync_xui():
    """Синхронизирует даты окончания из 3x-ui в локальную БД."""
    async def do():
        from datetime import datetime
        from xui_client import XUIClient

        updated = 0
        errors = 0

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT telegram_id, xui_email FROM users WHERE status='active'") as cur:
                users = await cur.fetchall()

        async with XUIClient() as xui:
            for u in users:
                try:
                    client = await xui.get_client(u["xui_email"])
                    expiry = client.get("expiryTime", 0)
                    if expiry > 0:
                        dt = datetime.fromtimestamp(expiry / 1000).strftime("%Y-%m-%d %H:%M:%S")
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute("UPDATE users SET expires_at = ? WHERE telegram_id = ?", (dt, u["telegram_id"]))
                            await db.commit()
                        updated += 1
                except Exception as e:
                    logger.warning(f"sync failed for {u['xui_email']}")
                    errors += 1

        await _audit(request.admin_user["id"], "sync_xui", None, f"updated={updated}, errors={errors}")
        return {"success": True, "updated": updated, "errors": errors}

    try:
        r = run_async(do())
    except Exception as e:
        logger.error("admin/sync failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
    return jsonify(r)


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
            if status == "web":
                where.append("source = 'web'")
            elif status != "all":
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

            sort = data.get("sort") or "created_desc"
            order_map = {
                "created_desc": "created_at DESC",
                "created_asc":  "created_at ASC",
                "name":         "LOWER(COALESCE(NULLIF(first_name,''), username, CAST(telegram_id AS TEXT))) ASC",
                "expires":      "CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END, expires_at ASC",
            }
            order_sql = order_map.get(sort, "created_at DESC")

            async with db.execute(
                f"""SELECT telegram_id, username, first_name, status, xui_email, source,
                           expires_at, invites_count, renew_count, created_at,
                           last_seen, invited_by
                    FROM users {where_sql}
                    ORDER BY {order_sql}
                    LIMIT ? OFFSET ?""",
                (*args, limit, offset),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

        from datetime import datetime
        now_ms = int(datetime.now().timestamp() * 1000)
        online_threshold_ms = 5 * 60 * 1000  # 5 минут

        # --- Онлайн-статус из 3x-ui через /clients/onlines ---
        # Это тот же список, что и в панели «В сети» — точное совпадение.
        online_emails = set()
        try:
            from xui_client import XUIClient
            async with XUIClient() as xui:
                res = await xui._post("/panel/api/clients/onlines", {})
                if res.get("success"):
                    online_emails = set(res.get("obj", []) or [])
        except Exception:
            logger.exception("Не удалось получить онлайн-статус из 3x-ui")

        for u in rows:
            email = u.get("xui_email")
            u["vpn_online"] = email in online_emails
            u["is_web"] = (u.get("source") == "web")

            # role: web / реферал / бот
            if u.get("source") == "web":
                u["role_label"] = "web"
                u["role_color"] = "web"
            elif u.get("invited_by"):
                u["role_label"] = "реферал"
                u["role_color"] = "referral"
            else:
                u["role_label"] = "бот"
                u["role_color"] = "bot"

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
        logger.error("admin/users failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@admin_api.route("/user", methods=["POST"])
@admin_required
def user_card():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def get_data():
        from database import get_user
        from xui_client import XUIClient
        from datetime import datetime

        u = await get_user(tg_id)
        if not u:
            return {"error": "Пользователь не найден"}

        result = dict(u)
        # Обрезаем микросекунды у expires_at
        if result.get("expires_at"):
            try:
                from datetime import datetime
                dt = result["expires_at"]
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                result["expires_at"] = dt.strftime("%d.%m.%y %H:%M")
            except Exception:
                pass
        result["is_blocked"] = False
        result["comment"] = ""
        result["traffic_up"] = None
        result["traffic_down"] = None
        result["is_online"] = False

        # Берём данные из 3x-ui, если есть email
        if u["xui_email"]:
            try:
                async with XUIClient() as xui:
                    client = await xui.get_client(u["xui_email"])
                    if client:
                        result["is_blocked"] = not client.get("enable", True)
                        result["comment"] = client.get("comment", "")

                        # Трафик
                        traffic = await xui.get_client_traffic(u["xui_email"])
                        if traffic:
                            up = traffic.get("up")
                            down = traffic.get("down")
                            if up is not None:
                                result["traffic_up"] = f"{up / (1024**3):.2f} GB"
                            if down is not None:
                                result["traffic_down"] = f"{down / (1024**3):.2f} GB"

                        # Онлайн
                        result["is_online"] = await xui.is_client_online(u["xui_email"])
            except Exception as e:
                logger.warning(f"Ошибка получения данных 3x-ui для {u['xui_email']}")

        # Дни до окончания
        if u["expires_at"]:
            try:
                exp = datetime.strptime(str(u["expires_at"])[:10], "%Y-%m-%d")
                result["days_left"] = (exp - datetime.now()).days
            except Exception:
                result["days_left"] = None

        return {"user": result}

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
        logger.error("admin/requests failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# ---------------- actions ----------------

@admin_api.route("/approve", methods=["POST"])
@admin_required
def approve():
    tg_id = int((request.json or {}).get("tg_id", 0))
    custom_comment = (request.json or {}).get("comment")

    async def do():
        from database import get_user, approve_user
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if not user:
            return {"error": "Пользователь не найден"}
        if user["status"] == "active":
            return {"error": "Уже активен"}

        user_part = f"@{user['username']}" if user["username"] else str(tg_id)
        comment = f"{user_part} | {custom_comment}" if custom_comment else f"{user_part} | bot"

        try:
            async with XUIClient() as xui:
                sub_id = await xui.add_client(
                    user["xui_email"],
                    comment=comment,
                    tg_id=tg_id,
                )
                await approve_user(tg_id, sub_id)
                sub_url = xui.build_sub_url(sub_id)
        except Exception as e:
            logger.error(f"approve failed for {tg_id}")
            return {"error": "Внутренняя ошибка сервера"}

        await _audit(request.admin_user["id"], "approve", tg_id, comment)
        return {"success": True, "sub_url": sub_url}

    try:
        r = run_async(do())
    except Exception as e:
        logger.error("admin/approve failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


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
        logger.error("admin/reject failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


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
        if not user["xui_email"]:
            return {"error": "У пользователя нет xui_email"}

        async with XUIClient() as xui:
            new_expiry = await xui.update_expiry(user["xui_email"], days=days)
            try:
                new_count = await increment_renew_count(tg_id)
                user_part = f"@{user['username']}" if user["username"] else str(tg_id)
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
        logger.error("admin/extend failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
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
        if user and user["xui_email"]:
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
        logger.error("admin/delete failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# ---------------- block / unblock ----------------

@admin_api.route("/block", methods=["POST"])
@admin_required
def block():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def do():
        from database import get_user
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if not user or not user["xui_email"]:
            return {"error": "Пользователь не найден или нет email"}

        async with XUIClient() as xui:
            client = await xui.get_client(user["xui_email"])
            if not client:
                return {"error": "Клиент не найден в 3x-ui"}

            result = await xui._post(f"/panel/api/clients/update/{user['xui_email']}", {
                "email": user["xui_email"],
                "enable": False,
                "limitIp": client.get("limitIp", 3),
                "totalGB": client.get("totalGB", 0),
                "expiryTime": client.get("expiryTime", 0),
            })
            if result.get("success"):
                # Меняем статус в БД на 'blocked'
                import aiosqlite
                from config import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET status = 'blocked' WHERE telegram_id = ?", (tg_id,))
                    await db.commit()
                await _audit(request.json.get("init_data"), "block", tg_id)
                return {"success": True}
            return {"error": "Ошибка 3x-ui"}

    try:
        r = run_async(do())
        if "error" in r:
            return jsonify(r), 400
        return jsonify(r)
    except Exception as e:
        logger.error("admin/block failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@admin_api.route("/unblock", methods=["POST"])
@admin_required
def unblock():
    tg_id = int((request.json or {}).get("tg_id", 0))

    async def do():
        from database import get_user
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if not user or not user["xui_email"]:
            return {"error": "Пользователь не найден или нет email"}

        async with XUIClient() as xui:
            client = await xui.get_client(user["xui_email"])
            if not client:
                return {"error": "Клиент не найден в 3x-ui"}

            result = await xui._post(f"/panel/api/clients/update/{user['xui_email']}", {
                "email": user["xui_email"],
                "enable": True,
                "limitIp": client.get("limitIp", 3),
                "totalGB": client.get("totalGB", 0),
                "expiryTime": client.get("expiryTime", 0),
            })
            if result.get("success"):
                # Возвращаем статус 'active'
                import aiosqlite
                from config import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET status = 'active' WHERE telegram_id = ?", (tg_id,))
                    await db.commit()
                await _audit(request.json.get("init_data"), "unblock", tg_id)
                return {"success": True}
            return {"error": "Ошибка 3x-ui"}

    try:
        r = run_async(do())
        if "error" in r:
            return jsonify(r), 400
        return jsonify(r)
    except Exception as e:
        logger.error("admin/unblock failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500






@admin_api.route("/broadcast", methods=["POST"])
def broadcast():
    """Отправляет рассылку всем пользователям."""
    data = request.json or {}
    text = data.get("text")
    silent = data.get("silent", False)

    if not text:
        return jsonify({"error": "Нет текста"}), 400

    async def do_broadcast():
        from aiogram import Bot
        from config import BOT_TOKEN
        import aiosqlite
        from config import DB_PATH

        bot = Bot(token=BOT_TOKEN)
        sent = 0
        failed = 0

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT telegram_id FROM users WHERE status = 'active'") as cur:
                    users = await cur.fetchall()

            for u in users:
                try:
                    await bot.send_message(u["telegram_id"], text, disable_notification=silent)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.05)
        finally:
            await bot.session.close()

        return {"sent": sent, "failed": failed}

    try:
        result = asyncio.run(do_broadcast())
        return jsonify({"success": True, "sent": result["sent"], "failed": result["failed"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

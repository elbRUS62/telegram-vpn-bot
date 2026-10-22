"""API-роуты админки Mini App. Все методы POST, init_data в теле."""
import asyncio
import logging
from functools import wraps

import aiosqlite
from flask import Blueprint, jsonify, request

from config import ADMIN_IDS, DB_PATH, MAX_USERS, BOT_NAME, XUI_PANELS
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


# ---------------- 3x-ui panel link ----------------

@admin_api.route("/xui", methods=["POST"])
@admin_required
def xui_panel_url():
    """Ссылка на панель 3x-ui. Только для админов: base path — секрет."""
    data = request.json or {}
    panel_id = (data.get("panel_id") or "").strip()
    panel = None
    if panel_id:
        panel = next((p for p in XUI_PANELS if p["id"] == panel_id), None)
    else:
        panel = XUI_PANELS[0] if XUI_PANELS else None
    if not panel:
        return jsonify({"error": "Панель 3x-ui не найдена"}), 404
    host = (panel.get("host") or "").rstrip("/")
    base = (panel.get("base_path") or "").strip("/")
    if not host:
        return jsonify({"error": "Панель 3x-ui не настроена"}), 503
    url = f"{host}/{base}/panel" if base else f"{host}/panel"
    return jsonify({
        "url": url,
        "panel_id": panel["id"],
        "name": panel.get("name") or panel["id"],
    })


# ---------------- 3x-ui monitoring ----------------

@admin_api.route("/monitor", methods=["POST"])
@admin_required
def monitor_status():
    """Текущее состояние всех панелей 3x-ui для карточки мониторинга."""
    from monitoring import collect_all_status_with_history

    try:
        return jsonify({"panels": run_async(collect_all_status_with_history())})
    except Exception:
        logger.exception("admin/monitor failed")
        return jsonify({
            "panels": [],
            "error": "Не удалось получить статус 3x-ui",
        }), 500


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
            elif status == "expiring":
                where.append(
                    "status='active' AND DATE(expires_at) "
                    "BETWEEN DATE('now') AND DATE('now','+3 days')"
                )
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
            logger.error("Не удалось получить онлайн-статус из 3x-ui")

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

        u = dict(u)  # sqlite3.Row → dict (чтобы работал .get())
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
        # Форматируем created_at и last_seen
        for key in ("created_at", "last_seen"):
            if result.get(key):
                try:
                    from datetime import datetime
                    dt = result[key]
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                    result[key] = dt.strftime("%d.%m.%y %H:%M")
                except Exception:
                    pass
        result["is_blocked"] = False
        result["comment"] = ""
        result["traffic_up"] = None
        result["traffic_down"] = None
        result["is_online"] = False
        result["vpn_online"] = False
        result["role_label"] = ""
        result["role_color"] = ""

        # Роль (web / реферал / бот)
        if u.get("source") == "web":
            result["role_label"] = "web"
            result["role_color"] = "web"
        elif u.get("invited_by"):
            result["role_label"] = "реферал"
            result["role_color"] = "referral"
        else:
            result["role_label"] = "бот"
            result["role_color"] = "bot"

        # Берём онлайн-статус одним запросом (до получения клиента)
        try:
            async with XUIClient() as xui_onl:
                res_onl = await xui_onl._post("/panel/api/clients/onlines", {})
                if res_onl.get("success"):
                    online_emails = set(res_onl.get("obj", []) or [])
                    result["vpn_online"] = (u.get("xui_email") in online_emails)
                    result["is_online"] = result["vpn_online"]
        except Exception:
            logger.error("user_card: onlines failed")

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

                        # Онлайн: через /clients/onlines (как в списке)
                        result["is_online"] = False
                        result["vpn_online"] = False
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


# ---------------- diagnostics ----------------

@admin_api.route("/diagnostics", methods=["POST"])
@admin_required
def user_diagnostics():
    data = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    if not tg_id:
        return jsonify({"error": "Не указан пользователь"}), 400

    from web.routes.api import _collect_diagnostics

    result = run_async(_collect_diagnostics(tg_id))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


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
                await _audit(request.admin_user["id"], "block", tg_id)
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
                await _audit(request.admin_user["id"], "unblock", tg_id)
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
        from config import BOT_TOKEN
        from telegram_api import Telegram

        sent = 0
        failed = 0

        async with Telegram(BOT_TOKEN) as tg:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT telegram_id FROM users WHERE status = 'active'") as cur:
                    users = await cur.fetchall()

            for u in users:
                result = await tg.send_message(
                    u["telegram_id"], text, disable_notification=silent
                )
                if result is None:
                    failed += 1
                else:
                    sent += 1
                await asyncio.sleep(0.05)

        return {"sent": sent, "failed": failed}

    try:
        result = asyncio.run(do_broadcast())
        # Логируем действие
        try:
            meta = f"sent={result['sent']}, failed={result['failed']}, text={text[:80]}"
            run_async(_audit(request.admin_user["id"], "broadcast", None, meta))
        except Exception:
            logger.error("_audit broadcast failed")
        return jsonify({"success": True, "sent": result["sent"], "failed": result["failed"]})
    except Exception as e:
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

# ---------------- audit ----------------

@admin_api.route("/audit", methods=["POST"])
@admin_required
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


# ---------------- support tickets ----------------

TICKET_CATEGORIES = {
    "connect": "Подключение",
    "payment": "Оплата",
    "account": "Аккаунт",
    "other": "Другое",
}
TICKET_STATUSES = {
    "open": "Открыт",
    "answered": "Ответ получен",
    "closed": "Закрыт",
}


def _ticket_dict(row):
    d = dict(row)
    d["category_label"] = TICKET_CATEGORIES.get(
        d.get("category"), d.get("category") or "Другое"
    )
    d["status_label"] = TICKET_STATUSES.get(
        d.get("status"), d.get("status") or "—"
    )
    d["last_text"] = (d.get("last_text") or "")[:160]
    return d


@admin_api.route("/tickets", methods=["POST"])
@admin_required
def tickets_list():
    data = request.json or {}
    status = data.get("status") or "active"
    q = (data.get("q") or "").strip().lower()
    try:
        page = max(1, int(data.get("page", 1)))
        limit = min(50, max(1, int(data.get("limit", 20))))
    except (TypeError, ValueError):
        page, limit = 1, 20
    offset = (page - 1) * limit

    async def get_data():
        where, args = [], []
        if status == "active":
            where.append("t.status IN ('open','answered')")
        elif status == "closed":
            where.append("t.status = 'closed'")
        elif status != "all":
            where.append("t.status = ?")
            args.append(status)

        if q:
            where.append(
                "(LOWER(t.subject) LIKE ? OR LOWER(t.username) LIKE ? "
                "OR LOWER(t.first_name) LIKE ? OR CAST(t.telegram_id AS TEXT) LIKE ?)"
            )
            args.extend([f"%{q}%"] * 4)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(f"""
                SELECT t.*,
                    (SELECT m.text FROM support_messages m
                     WHERE m.ticket_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_text,
                    (SELECT COUNT(*) FROM support_messages m
                     WHERE m.ticket_id = t.id) AS messages_count
                FROM support_tickets t
                {where_sql}
                ORDER BY
                    CASE t.status WHEN 'open' THEN 0 WHEN 'answered' THEN 1 ELSE 2 END,
                    t.updated_at DESC, t.id DESC
                LIMIT ? OFFSET ?
            """, (*args, limit, offset)) as cur:
                tickets = [_ticket_dict(r) for r in await cur.fetchall()]

            async with db.execute(
                f"SELECT COUNT(*) FROM support_tickets t {where_sql}", args
            ) as cur:
                total = (await cur.fetchone())[0]

            async with db.execute("""
                SELECT
                    SUM(CASE WHEN status IN ('open','answered') THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status != 'closed' AND unread_admin = 1 THEN 1 ELSE 0 END)
                FROM support_tickets
            """) as cur:
                counts = await cur.fetchone()

        return {
            "tickets": tickets,
            "total": total,
            "page": page,
            "has_more": offset + len(tickets) < total,
            "tickets_open": counts[0] or 0,
            "tickets_unread": counts[1] or 0,
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception:
        logger.exception("admin/tickets failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@admin_api.route("/ticket", methods=["POST"])
@admin_required
def ticket_detail():
    data = request.json or {}
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400

    async def do():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)
            ) as cur:
                ticket = await cur.fetchone()
            if not ticket:
                return {"error": "Обращение не найдено"}

            await db.execute(
                "UPDATE support_tickets SET unread_admin = 0 WHERE id = ?",
                (ticket_id,),
            )
            await db.commit()

            async with db.execute(
                "SELECT id, sender, admin_id, text, created_at "
                "FROM support_messages WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            ) as cur:
                messages = [dict(r) for r in await cur.fetchall()]

        return {"ticket": _ticket_dict(ticket), "messages": messages}

    try:
        result = run_async(do())
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception:
        logger.exception("admin/ticket failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@admin_api.route("/ticket/reply", methods=["POST"])
@admin_required
def ticket_reply():
    data = request.json or {}
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400
    text = (data.get("text") or "").strip()
    if len(text) < 2:
        return jsonify({"error": "Сообщение слишком короткое"}), 400
    if len(text) > 3000:
        return jsonify({"error": "Слишком длинный текст"}), 400

    admin_id = request.admin_user["id"]

    async def do():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)
            ) as cur:
                ticket = await cur.fetchone()
            if not ticket:
                return {"error": "Обращение не найдено"}

            await db.execute(
                "INSERT INTO support_messages(ticket_id, sender, admin_id, text) "
                "VALUES (?, 'admin', ?, ?)",
                (ticket_id, admin_id, text),
            )
            await db.execute("""
                UPDATE support_tickets
                SET status = 'answered', unread_admin = 0, unread_user = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ticket_id,))
            await db.commit()

        await _audit(admin_id, "ticket_reply", ticket_id, f"len={len(text)}")
        return {"success": True, "telegram_id": ticket["telegram_id"]}

    try:
        result = run_async(do())
        if "error" in result:
            return jsonify(result), 400
        from web.utils.telegram import notify_user
        notify_user(
            result.get("telegram_id"),
            f"💬 Ответ по обращению #{ticket_id}\n\n{text[:1200]}\n\n"
            "Открой Mini App → Техподдержка, чтобы ответить.",
        )
        return jsonify({"success": True})
    except Exception:
        logger.exception("admin/ticket/reply failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


@admin_api.route("/ticket/close", methods=["POST"])
@admin_required
def ticket_close():
    data = request.json or {}
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400

    admin_id = request.admin_user["id"]

    async def do():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT telegram_id, status FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ) as cur:
                ticket = await cur.fetchone()
            if not ticket:
                return {"error": "Обращение не найдено"}

            await db.execute("""
                UPDATE support_tickets
                SET status = 'closed', unread_admin = 0, unread_user = 1,
                    closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ticket_id,))
            await db.commit()

        await _audit(admin_id, "ticket_close", ticket_id)
        return {"success": True, "telegram_id": ticket["telegram_id"]}

    try:
        result = run_async(do())
        if "error" in result:
            return jsonify(result), 400
        from web.utils.telegram import notify_user
        notify_user(
            result.get("telegram_id"),
            f"✅ Обращение #{ticket_id} закрыто.\n\n"
            "Если проблема осталась — создай новое обращение в "
            "Mini App → Техподдержка.",
        )
        return jsonify({"success": True})
    except Exception:
        logger.exception("admin/ticket/close failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500



import csv
import io

import aiosqlite
from flask import Response, jsonify, request

from config import DB_PATH, XUI_PANELS
from web.utils.async_helper import run_async
from web.utils.subscription_days import days_left_from_expiry, plan_days_for_source

from .common import (
    _audit,
    admin_api,
    admin_required,
    clean_reason,
    logger,
    superadmin_required,
)

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
                           last_seen, invited_by,
                           (SELECT role FROM admins
                            WHERE admins.telegram_id = users.telegram_id
                              AND admins.is_active = 1) AS admin_role
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
            u["plan_days"] = plan_days_for_source(u.get("source"))
            admin_role = u.get("admin_role")
            u["is_admin"] = bool(admin_role)
            u["is_superadmin"] = admin_role == "superadmin"

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


@admin_api.route("/users/export", methods=["POST"])
@superadmin_required
def users_export():
    data = request.json or {}
    q = (data.get("q") or "").strip().lower()
    status = data.get("status") or "all"

    async def get_rows():
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
            async with db.execute(
                f"""SELECT telegram_id, username, first_name, status, xui_email,
                           source, expires_at, invites_count, renew_count,
                           created_at, last_seen
                    FROM users {where_sql}
                    ORDER BY created_at DESC
                    LIMIT 10000""",
                args,
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    rows = run_async(get_rows())
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "telegram_id", "username", "first_name", "status", "xui_email",
        "source", "expires_at", "invites_count", "renew_count",
        "created_at", "last_seen",
    ])
    for row in rows:
        writer.writerow([
            row.get("telegram_id"), row.get("username") or "",
            row.get("first_name") or "", row.get("status") or "",
            row.get("xui_email") or "", row.get("source") or "",
            row.get("expires_at") or "", row.get("invites_count") or 0,
            row.get("renew_count") or 0, row.get("created_at") or "",
            row.get("last_seen") or "",
        ])
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=skrepnet-users.csv"},
    )


@admin_api.route("/users/bulk", methods=["POST"])
@superadmin_required
def users_bulk():
    data = request.json or {}
    action = data.get("action")
    if action not in ("block", "delete"):
        return jsonify({"error": "Недопустимое действие"}), 400
    reason = clean_reason(data.get("reason"))
    ids = []
    for value in (data.get("ids") or [])[:100]:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not ids:
        return jsonify({"error": "Пользователи не выбраны"}), 400

    async def do():
        from database import get_user, delete_user
        from xui_client import XUIClient

        updated = 0
        errors = 0
        for tg_id in ids:
            try:
                user = await get_user(tg_id)
                if not user:
                    errors += 1
                    continue
                if action == "block":
                    if not user["xui_email"]:
                        errors += 1
                        continue
                    async with XUIClient() as xui:
                        client = await xui.get_client(user["xui_email"])
                        if not client:
                            errors += 1
                            continue
                        result = await xui._post(
                            f"/panel/api/clients/update/{user['xui_email']}",
                            {
                                "email": user["xui_email"],
                                "enable": False,
                                "limitIp": client.get("limitIp", 3),
                                "totalGB": client.get("totalGB", 0),
                                "expiryTime": client.get("expiryTime", 0),
                            },
                        )
                    if not result.get("success"):
                        errors += 1
                        continue
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute(
                            "UPDATE users SET status = 'blocked' WHERE telegram_id = ?",
                            (tg_id,),
                        )
                        await db.commit()
                else:
                    if user["xui_email"]:
                        try:
                            async with XUIClient() as xui:
                                await xui.delete_client(user["xui_email"])
                        except Exception:
                            logger.warning("bulk delete: xui delete failed for %s", tg_id)
                    await delete_user(tg_id)
                updated += 1
            except Exception:
                logger.warning("bulk action failed for %s", tg_id)
                errors += 1

        await _audit(
            request.admin_user["id"],
            f"bulk_{action}",
            None,
            f"updated={updated}, errors={errors}"
            + (f", reason={reason}" if reason else ""),
        )
        return {"success": True, "updated": updated, "errors": errors}

    try:
        return jsonify(run_async(do()))
    except Exception:
        logger.error("admin/users/bulk failed")
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
        from permissions import get_admin_role

        admin_role = get_admin_role(tg_id)
        result["admin_role"] = admin_role
        result["is_admin"] = admin_role is not None
        result["is_superadmin"] = admin_role == "superadmin"
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
        result["plan_days"] = plan_days_for_source(u.get("source"))
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
        result["days_left"] = days_left_from_expiry(u["expires_at"])

        return {"user": result}

    r = run_async(get_data())
    if "error" in r:
        return jsonify(r), 404
    return jsonify(r)

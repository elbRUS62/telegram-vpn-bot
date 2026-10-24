import csv
import io

import aiosqlite
from flask import Response, jsonify, request

from config import DB_PATH
from web.utils.async_helper import run_async

from .common import _audit, admin_api, admin_required, superadmin_required, logger

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


@admin_api.route("/tickets/export", methods=["POST"])
@superadmin_required
def tickets_export():
    async def get_rows():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT t.id, t.telegram_id, t.username, t.first_name,
                          t.subject, t.category, t.status, t.unread_admin,
                          t.unread_user, t.created_at, t.updated_at, t.closed_at,
                          (SELECT text FROM support_messages m
                           WHERE m.ticket_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_text
                   FROM support_tickets t
                   ORDER BY t.created_at DESC
                   LIMIT 10000"""
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]

    rows = run_async(get_rows())
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "id", "telegram_id", "username", "first_name", "subject",
        "category", "status", "unread_admin", "unread_user",
        "created_at", "updated_at", "closed_at", "last_text",
    ])
    for row in rows:
        writer.writerow([
            row.get("id"), row.get("telegram_id"), row.get("username") or "",
            row.get("first_name") or "", row.get("subject") or "",
            TICKET_CATEGORIES.get(row.get("category"), row.get("category") or ""),
            TICKET_STATUSES.get(row.get("status"), row.get("status") or ""),
            row.get("unread_admin") or 0, row.get("unread_user") or 0,
            row.get("created_at") or "", row.get("updated_at") or "",
            row.get("closed_at") or "", (row.get("last_text") or "")[:500],
        ])
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=skrepnet-tickets.csv"},
    )


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

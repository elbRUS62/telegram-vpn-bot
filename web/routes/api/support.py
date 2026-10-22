"""Тикеты поддержки в Mini App: пользовательская часть."""
import logging

import aiosqlite
from flask import Blueprint, jsonify, request

from config import DB_PATH, SUPPORT_USERNAME
from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data
from web.utils.telegram import notify_admins

logger = logging.getLogger(__name__)

support_api = Blueprint("miniapp_support_api", __name__, url_prefix="/api/miniapp/support")

CATEGORIES = {
    "connect": "Подключение",
    "payment": "Оплата",
    "account": "Аккаунт",
    "other": "Другое",
}
STATUS_LABELS = {
    "open": "Открыт",
    "answered": "Ответ получен",
    "closed": "Закрыт",
}
MAX_SUBJECT = 120
MAX_TEXT = 3000


def _auth_user():
    data = request.json or {}
    user = validate_init_data(data.get("init_data", ""))
    if not user:
        return None, data
    return user, data


def _ticket_dict(row):
    d = dict(row)
    d["category_label"] = CATEGORIES.get(d.get("category"), d.get("category") or "Другое")
    d["status_label"] = STATUS_LABELS.get(d.get("status"), d.get("status") or "—")
    d["last_text"] = (d.get("last_text") or "")[:160]
    return d


@support_api.route("/list", methods=["POST"])
def tickets_list():
    user, _ = _auth_user()
    if not user:
        return jsonify({"error": "Неверная авторизация"}), 401

    telegram_id = user.get("id")

    async def get_data():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT t.*,
                    (SELECT m.text FROM support_messages m
                     WHERE m.ticket_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_text,
                    (SELECT COUNT(*) FROM support_messages m
                     WHERE m.ticket_id = t.id) AS messages_count
                FROM support_tickets t
                WHERE t.telegram_id = ?
                ORDER BY
                    CASE t.status WHEN 'open' THEN 0 WHEN 'answered' THEN 1 ELSE 2 END,
                    t.updated_at DESC, t.id DESC
            """, (telegram_id,)) as cur:
                tickets = [_ticket_dict(r) for r in await cur.fetchall()]

        return {
            "tickets": tickets,
            "unread_count": sum(1 for t in tickets if t.get("unread_user")),
            "support_username": SUPPORT_USERNAME,
        }

    return jsonify(run_async(get_data()))


@support_api.route("/ticket", methods=["POST"])
def ticket_detail():
    user, data = _auth_user()
    if not user:
        return jsonify({"error": "Неверная авторизация"}), 401

    telegram_id = user.get("id")
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400

    async def get_data():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM support_tickets WHERE id = ? AND telegram_id = ?",
                (ticket_id, telegram_id),
            ) as cur:
                ticket = await cur.fetchone()
            if not ticket:
                return {"error": "Обращение не найдено"}

            await db.execute(
                "UPDATE support_tickets SET unread_user = 0 WHERE id = ?",
                (ticket_id,),
            )
            await db.commit()

            async with db.execute(
                "SELECT id, sender, text, created_at FROM support_messages "
                "WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            ) as cur:
                messages = [dict(r) for r in await cur.fetchall()]

        return {
            "ticket": _ticket_dict(ticket),
            "messages": messages,
        }

    result = run_async(get_data())
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@support_api.route("/create", methods=["POST"])
def ticket_create():
    user, data = _auth_user()
    if not user:
        return jsonify({"error": "Неверная авторизация"}), 401

    telegram_id = user.get("id")
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    category = (data.get("category") or "other").strip()

    if category not in CATEGORIES:
        category = "other"
    if len(subject) < 3:
        return jsonify({"error": "Укажи тему обращения (минимум 3 символа)"}), 400
    if len(message) < 3:
        return jsonify({"error": "Опиши проблему подробнее"}), 400
    if len(subject) > MAX_SUBJECT or len(message) > MAX_TEXT:
        return jsonify({"error": f"Слишком длинный текст (максимум {MAX_TEXT} символов)"}), 400

    async def do_create():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT COUNT(*) FROM support_tickets "
                "WHERE telegram_id = ? AND status != 'closed'",
                (telegram_id,),
            ) as cur:
                open_count = (await cur.fetchone())[0]

            if open_count >= 3:
                return {"error": "У тебя уже 3 открытых обращения. Дождись ответа."}

            async with db.execute(
                "SELECT COUNT(*) FROM support_tickets "
                "WHERE telegram_id = ? AND created_at >= datetime('now', '-10 minutes')",
                (telegram_id,),
            ) as cur:
                recent = (await cur.fetchone())[0]

            if recent >= 2:
                return {"error": "Слишком часто. Подожди немного перед новым обращением."}

            async with db.execute("""
                INSERT INTO support_tickets
                (telegram_id, username, first_name, subject, category,
                 status, unread_admin, unread_user)
                VALUES (?, ?, ?, ?, ?, 'open', 1, 0)
            """, (
                telegram_id,
                user.get("username") or "",
                user.get("first_name") or "",
                subject,
                category,
            )) as cur:
                ticket_id = cur.lastrowid
            await db.execute(
                "INSERT INTO support_messages(ticket_id, sender, text) VALUES (?, 'user', ?)",
                (ticket_id, message),
            )
            await db.commit()

        return {"success": True, "ticket_id": ticket_id}

    result = run_async(do_create())
    if "error" in result:
        return jsonify(result), 400

    who = f"@{user.get('username')}" if user.get("username") else (user.get("first_name") or f"ID {telegram_id}")
    notify_admins(
        f"🎫 Новый тикет #{result['ticket_id']}\n"
        f"👤 {who} ({telegram_id})\n"
        f"📂 {CATEGORIES[category]}\n"
        f"📝 {subject}\n\n"
        f"{message[:1200]}\n\n"
        "Открой Mini App → Админ → 🎫 Тикеты."
    )
    return jsonify(result)


@support_api.route("/reply", methods=["POST"])
def ticket_reply():
    user, data = _auth_user()
    if not user:
        return jsonify({"error": "Неверная авторизация"}), 401

    telegram_id = user.get("id")
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400
    message = (data.get("message") or "").strip()

    if len(message) < 2:
        return jsonify({"error": "Сообщение слишком короткое"}), 400
    if len(message) > MAX_TEXT:
        return jsonify({"error": f"Слишком длинный текст (максимум {MAX_TEXT} символов)"}), 400

    async def do_reply():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, status FROM support_tickets "
                "WHERE id = ? AND telegram_id = ?",
                (ticket_id, telegram_id),
            ) as cur:
                ticket = await cur.fetchone()
            if not ticket:
                return {"error": "Обращение не найдено"}
            if ticket["status"] == "closed":
                return {"error": "Обращение закрыто. Создай новое."}

            async with db.execute("""
                SELECT COUNT(*) FROM support_messages m
                JOIN support_tickets t ON t.id = m.ticket_id
                WHERE t.telegram_id = ? AND m.sender = 'user'
                  AND m.created_at >= datetime('now', '-5 minutes')
            """, (telegram_id,)) as cur:
                recent = (await cur.fetchone())[0]
            if recent >= 10:
                return {"error": "Слишком много сообщений. Подожди пару минут."}

            await db.execute(
                "INSERT INTO support_messages(ticket_id, sender, text) "
                "VALUES (?, 'user', ?)",
                (ticket_id, message),
            )
            await db.execute("""
                UPDATE support_tickets
                SET status = 'open', unread_admin = 1, unread_user = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ticket_id,))
            await db.commit()

        return {"success": True}

    result = run_async(do_reply())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@support_api.route("/close", methods=["POST"])
def ticket_close():
    user, data = _auth_user()
    if not user:
        return jsonify({"error": "Неверная авторизация"}), 401

    telegram_id = user.get("id")
    try:
        ticket_id = int(data.get("ticket_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Неверный номер обращения"}), 400

    async def do_close():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id FROM support_tickets WHERE id = ? AND telegram_id = ?",
                (ticket_id, telegram_id),
            ) as cur:
                if not await cur.fetchone():
                    return {"error": "Обращение не найдено"}
            await db.execute("""
                UPDATE support_tickets
                SET status = 'closed', unread_admin = 0, unread_user = 0,
                    closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ticket_id,))
            await db.commit()
        return {"success": True}

    result = run_async(do_close())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

import asyncio

import aiosqlite
from flask import jsonify, request

from config import DB_PATH
from web.utils.async_helper import run_async

from .common import _audit, admin_api, admin_required, logger

@admin_api.route("/broadcast", methods=["POST"])
@admin_required
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

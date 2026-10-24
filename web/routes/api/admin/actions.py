import aiosqlite
from flask import jsonify, request

from config import DB_PATH
from web.utils.async_helper import run_async

from .common import (
    VALID_DAYS,
    _audit,
    admin_api,
    admin_required,
    clean_reason,
    logger,
    superadmin_required,
)

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
                sub_id = await xui.get_or_create_client(
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
@superadmin_required
def delete():
    data = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    reason = clean_reason(data.get("reason"))

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
        await _audit(
            request.admin_user["id"],
            "delete",
            tg_id,
            f"reason={reason}" if reason else "",
        )
        return {"success": True}

    try:
        return jsonify(run_async(do()))
    except Exception as e:
        logger.error("admin/delete failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

@admin_api.route("/block", methods=["POST"])
@admin_required
def block():
    data = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    reason = clean_reason(data.get("reason"))

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
                await _audit(
                    request.admin_user["id"],
                    "block",
                    tg_id,
                    f"reason={reason}" if reason else "",
                )
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


@admin_api.route("/comment", methods=["POST"])
@admin_required
def update_comment():
    data = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    comment = clean_reason(data.get("comment"))

    async def do():
        from database import get_user
        from xui_client import XUIClient

        user = await get_user(tg_id)
        if not user or not user["xui_email"]:
            return {"error": "Пользователь не найден"}

        async with XUIClient() as xui:
            updated = await xui.update_comment(user["xui_email"], comment)
        if not updated:
            return {"error": "Не удалось обновить комментарий в 3x-ui"}

        await _audit(
            request.admin_user["id"],
            "comment",
            tg_id,
            f"comment={comment}" if comment else "comment=",
        )
        return {"success": True, "comment": comment}

    try:
        r = run_async(do())
    except Exception:
        logger.error("admin/comment failed")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)

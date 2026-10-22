from flask import jsonify, request

from web.utils.async_helper import run_async

from .common import admin_api, admin_required, _audit, logger

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

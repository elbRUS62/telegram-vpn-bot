from flask import jsonify, request

from web.utils.async_helper import run_async

from .common import admin_api, admin_required

@admin_api.route("/diagnostics", methods=["POST"])
@admin_required
def user_diagnostics():
    data = request.json or {}
    tg_id = int(data.get("tg_id", 0))
    if not tg_id:
        return jsonify({"error": "Не указан пользователь"}), 400

    from web.routes.api.diagnostics import _collect_diagnostics

    result = run_async(_collect_diagnostics(tg_id))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

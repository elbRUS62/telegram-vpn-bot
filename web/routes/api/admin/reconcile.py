from flask import jsonify, request

from reconciliation import get_last_reconcile, reconcile_xui
from web.utils.async_helper import run_async

from .common import _audit, admin_api, admin_required, logger


@admin_api.route("/reconcile", methods=["POST"])
@admin_required
def run_reconcile():
    data = request.json or {}
    dry_run = bool(data.get("dry_run", False))

    try:
        result = run_async(reconcile_xui(dry_run=dry_run))
    except Exception:
        logger.exception("admin/reconcile failed")
        return jsonify({"error": "Не удалось выполнить сверку"}), 500

    if isinstance(result, dict) and result.get("error"):
        return jsonify(result), 400

    try:
        run_async(_audit(
            request.admin_user["id"],
            "reconcile_xui",
            None,
            f"dry_run={dry_run}, fixed={result.get('fixed_disabled', 0)}/{result.get('fixed_expiry', 0)}",
        ))
    except Exception:
        pass

    return jsonify(result)


@admin_api.route("/reconcile/status", methods=["POST"])
@admin_required
def reconcile_status():
    try:
        result = run_async(get_last_reconcile())
    except Exception:
        logger.exception("admin/reconcile/status failed")
        return jsonify({"error": "Не удалось получить статус сверки"}), 500
    return jsonify({"result": result})

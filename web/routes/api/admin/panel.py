import logging

from flask import jsonify, request

from config import XUI_PANELS
from web.utils.async_helper import run_async

from .common import admin_api, admin_required, logger

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

@admin_api.route("/monitor", methods=["POST"])
@admin_required
def monitor_status():
    """Текущее состояние всех панелей 3x-ui для карточки мониторинга."""
    from monitoring import collect_all_status_with_history

    data = request.json or {}
    try:
        hours = int(data.get("hours", 24))
    except (TypeError, ValueError):
        hours = 24
    if hours not in (24, 168):
        hours = 24

    try:
        return jsonify({
            "hours": hours,
            "panels": run_async(
                collect_all_status_with_history(hours=hours, max_points=288)
            ),
        })
    except Exception:
        logger.exception("admin/monitor failed")
        return jsonify({
            "panels": [],
            "error": "Не удалось получить статус 3x-ui",
        }), 500

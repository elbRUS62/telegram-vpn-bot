"""Публичный healthcheck для веб-процесса, базы, бота и панелей 3x-ui."""

import time
from datetime import datetime, timezone

import aiosqlite
from flask import Blueprint, jsonify

from config import BOT_VERSION, DB_PATH, XUI_PANELS
from database import get_state_value
from web.utils.async_helper import run_async

health_bp = Blueprint("health", __name__)

BOT_HEARTBEAT_MAX_AGE = 180
PANEL_CHECK_MAX_AGE = 900


async def _collect_health() -> dict:
    now = int(time.time())

    db_ok = False
    db_error = None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
        db_ok = True
    except Exception as error:
        db_error = type(error).__name__

    heartbeat_raw = await get_state_value("bot:heartbeat")
    try:
        heartbeat = int(heartbeat_raw) if heartbeat_raw is not None else None
    except (TypeError, ValueError):
        heartbeat = None
    heartbeat_age = now - heartbeat if heartbeat is not None else None
    bot_ok = heartbeat_age is not None and heartbeat_age <= BOT_HEARTBEAT_MAX_AGE

    panels = []
    for panel in XUI_PANELS:
        panel_id = panel.get("id") or "panel"
        check_raw = await get_state_value(f"{panel_id}:last_check")
        ok_raw = await get_state_value(f"{panel_id}:last_ok")
        try:
            last_check = int(check_raw) if check_raw is not None else None
        except (TypeError, ValueError):
            last_check = None
        last_check_age = now - last_check if last_check is not None else None
        panel_ok = (
            str(ok_raw) == "1"
            and last_check_age is not None
            and last_check_age <= PANEL_CHECK_MAX_AGE
        )
        panels.append({
            "id": panel_id,
            "name": panel.get("name") or panel_id,
            "ok": panel_ok,
            "last_check_age_seconds": last_check_age,
        })

    panels_ok = bool(panels) and all(panel["ok"] for panel in panels)
    status = "ok" if db_ok and bot_ok and panels_ok else "degraded"
    if not db_ok:
        status = "error"

    return {
        "status": status,
        "version": BOT_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db": {"ok": db_ok, "error": db_error},
        "bot": {
            "ok": bot_ok,
            "heartbeat_age_seconds": heartbeat_age,
        },
        "panels": panels,
    }


@health_bp.route("/health", methods=["GET"])
@health_bp.route("/healthz", methods=["GET"])
def health():
    result = run_async(_collect_health())
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response, 200 if result["status"] == "ok" else 503

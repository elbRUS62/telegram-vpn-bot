import os
import subprocess

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


@admin_api.route("/errors", methods=["POST"])
@admin_required
def errors_log():
    """Последние ошибки web- и bot-сервисов из journald."""
    try:
        journalctl = (
            "/usr/bin/journalctl"
            if os.path.exists("/usr/bin/journalctl")
            else "journalctl"
        )
        result = subprocess.run(
            [
                journalctl,
                "-u", "skrepnet-web",
                "-u", "skrepnet-bot",
                "--since", "24 hours ago",
                "--no-pager",
                "-o", "cat",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        markers = ("ERROR", "Traceback", "CRITICAL", "Exception", "SIGKILL", "out of memory")
        lines = [
            line for line in (result.stdout or "").splitlines()
            if any(marker in line for marker in markers)
        ]
        return jsonify({"lines": lines[-120:], "count": len(lines)})
    except Exception:
        return jsonify({"error": "Не удалось прочитать журнал"}), 500

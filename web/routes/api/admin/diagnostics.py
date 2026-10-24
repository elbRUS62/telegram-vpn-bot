import os
import subprocess
from datetime import datetime, timedelta, timezone

import aiosqlite
from flask import jsonify, request

from config import DB_PATH
from web.utils.async_helper import run_async

from .common import admin_api, admin_required, superadmin_required

@admin_api.route("/diagnostics", methods=["POST"])
@superadmin_required
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


@admin_api.route("/diagnostics/stats", methods=["POST"])
@admin_required
def diagnostics_stats():
    data = request.json or {}
    try:
        days = max(1, min(30, int(data.get("days", 7))))
    except (TypeError, ValueError):
        days = 7
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:00")

    async def get_data():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            async def rows(sql, *args):
                async with db.execute(sql, args) as cur:
                    return [dict(row) for row in await cur.fetchall()]

            summary = (await rows("""
                SELECT
                    COALESCE(SUM(count), 0) AS total,
                    COALESCE(SUM(CASE WHEN ok = 1 THEN count ELSE 0 END), 0) AS ok_count,
                    COALESCE(SUM(CASE WHEN ok = 0 THEN count ELSE 0 END), 0) AS fail_count
                FROM diagnostic_stats
                WHERE bucket >= ?
            """, cutoff))[0]

            by_operator = await rows("""
                SELECT COALESCE(operator, 'unknown') AS operator,
                       asn,
                       COALESCE(SUM(count), 0) AS total,
                       COALESCE(SUM(CASE WHEN ok = 1 THEN count ELSE 0 END), 0) AS ok_count
                FROM diagnostic_stats
                WHERE bucket >= ?
                GROUP BY operator, asn
                ORDER BY total DESC
                LIMIT 30
            """, cutoff)

            by_stage = await rows("""
                SELECT stage,
                       COALESCE(SUM(count), 0) AS total,
                       COALESCE(SUM(CASE WHEN ok = 1 THEN count ELSE 0 END), 0) AS ok_count
                FROM diagnostic_stats
                WHERE bucket >= ? AND stage != 'ok'
                GROUP BY stage
                ORDER BY total DESC
            """, cutoff)

            by_timezone = await rows("""
                SELECT timezone,
                       COALESCE(SUM(count), 0) AS total,
                       COALESCE(SUM(CASE WHEN ok = 1 THEN count ELSE 0 END), 0) AS ok_count
                FROM diagnostic_stats
                WHERE bucket >= ?
                GROUP BY timezone
                ORDER BY total DESC
                LIMIT 30
            """, cutoff)

            hourly = await rows("""
                SELECT bucket,
                       COALESCE(SUM(count), 0) AS total,
                       COALESCE(SUM(CASE WHEN ok = 1 THEN count ELSE 0 END), 0) AS ok_count
                FROM diagnostic_stats
                WHERE bucket >= ?
                GROUP BY bucket
                ORDER BY bucket ASC
                LIMIT 168
            """, cutoff)

            def rate(item):
                total = int(item.get("total") or 0)
                ok_count = int(item.get("ok_count") or 0)
                return round(ok_count * 100 / total, 1) if total else 0

            summary["success_rate"] = rate(summary)
            for item in by_operator + by_stage + by_timezone + hourly:
                item["success_rate"] = rate(item)

        return {
            "days": days,
            "summary": summary,
            "by_operator": by_operator,
            "by_stage": by_stage,
            "by_timezone": by_timezone,
            "hourly": hourly,
        }

    try:
        return jsonify(run_async(get_data()))
    except Exception:
        return jsonify({"error": "Не удалось загрузить диагностику"}), 500


@admin_api.route("/errors", methods=["POST"])
@superadmin_required
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

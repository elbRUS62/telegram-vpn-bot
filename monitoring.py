"""Мониторинг 3x-ui: сбор метрик и фоновые алерты.

Модуль не импортирует aiogram, чтобы его можно было безопасно вызывать
из веб-процесса. Уведомления отправляет scheduler через переданный Bot.
"""
import asyncio
import logging
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import aiosqlite

from config import ADMIN_IDS, DB_PATH, XUI_PANELS
from xui_client import XUIClient

logger = logging.getLogger(__name__)

CACHE_TTL = 15
_cached_statuses = {}

CPU_ALERT = 90
MEM_ALERT = 90
DISK_ALERT = 85
CERT_ALERT_DAYS = 14
API_FAIL_ALERT_AFTER = 2
API_FAIL_COOLDOWN = 30 * 60
METRIC_COOLDOWN = 60 * 60
CERT_COOLDOWN = 24 * 60 * 60
XRAY_COOLDOWN = 30 * 60


def _pct(used, total):
    try:
        if not total:
            return None
        return round(float(used) / float(total) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _panel_label(panel):
    return (panel or {}).get("name") or (panel or {}).get("id") or "3x-ui"


def _cert_info(panel):
    """Возвращает (дней_до_окончания, ошибка) для TLS-сертификата панели."""
    try:
        parts = urlsplit((panel or {}).get("host") or "")
        if parts.scheme != "https" or not parts.hostname:
            return None, None
        host = parts.hostname
        port = parts.port or 443
        context = ssl.create_default_context()
        if not panel.get("verify_tls", True):
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=6) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return None, "notAfter отсутствует"
        expires = datetime.fromtimestamp(
            ssl.cert_time_to_seconds(not_after), tz=timezone.utc
        )
        days = (expires - datetime.now(timezone.utc)).days
        return days, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:200]


async def _get_cert_info(panel):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _cert_info, panel)


def _new_status(panel):
    return {
        "panel_id": panel.get("id") or "panel",
        "panel_name": _panel_label(panel),
        "panel_host": panel.get("host"),
        "ok": False,
        "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_ms": None,
        "cert_days_left": None,
        "cert_error": None,
        "cpu_percent": None,
        "cpu_cores": None,
        "cpu_speed_mhz": None,
        "mem_used": None,
        "mem_total": None,
        "mem_percent": None,
        "swap_used": None,
        "swap_total": None,
        "disk_used": None,
        "disk_total": None,
        "disk_percent": None,
        "loads": [],
        "xray_state": None,
        "xray_version": None,
        "panel_version": None,
        "uptime": None,
        "online_count": None,
        "inbounds_count": None,
        "traffic_up": None,
        "traffic_down": None,
        "traffic_total": None,
    }


async def collect_status(panel=None, force: bool = False) -> dict:
    """Собирает состояние одной панели. Результат кэшируется на 15 секунд."""
    panel = panel or XUI_PANELS[0]
    panel_id = panel.get("id") or "panel"
    now = time.monotonic()
    cached = _cached_statuses.get(panel_id)
    if not force and cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    result = _new_status(panel)

    cert_days, cert_error = await _get_cert_info(panel)
    result["cert_days_left"] = cert_days
    result["cert_error"] = cert_error

    try:
        async with XUIClient(panel) as xui:
            started = time.monotonic()
            status = await xui.get_server_status()
            result["api_ms"] = int((time.monotonic() - started) * 1000)

            mem = status.get("mem") or {}
            swap = status.get("swap") or {}
            disk = status.get("disk") or {}
            xray = status.get("xray") or {}

            result.update({
                "ok": True,
                "cpu_percent": round(float(status.get("cpu") or 0), 1),
                "cpu_cores": status.get("cpuCores"),
                "cpu_speed_mhz": status.get("cpuSpeedMhz"),
                "mem_used": mem.get("current"),
                "mem_total": mem.get("total"),
                "mem_percent": _pct(mem.get("current"), mem.get("total")),
                "swap_used": swap.get("current"),
                "swap_total": swap.get("total"),
                "disk_used": disk.get("current"),
                "disk_total": disk.get("total"),
                "disk_percent": _pct(disk.get("current"), disk.get("total")),
                "loads": status.get("loads") or [],
                "xray_state": xray.get("state"),
                "xray_version": xray.get("version"),
                "panel_version": status.get("panelVersion"),
                "uptime": status.get("uptime"),
            })

            # Инбаунды и онлайн-клиенты не должны ломать основной статус.
            try:
                inbounds = await xui.get_inbounds()
                result["inbounds_count"] = len(inbounds)
                up = sum(int(i.get("up") or 0) for i in inbounds)
                down = sum(int(i.get("down") or 0) for i in inbounds)
                result["traffic_up"] = up
                result["traffic_down"] = down
                result["traffic_total"] = up + down
            except Exception as e:
                logger.warning("monitor[%s]: inbounds failed: %s", panel_id, e)

            try:
                online = await xui.get_online_clients()
                result["online_count"] = len(online)
            except Exception as e:
                logger.warning("monitor[%s]: online clients failed: %s", panel_id, e)

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:300]
        logger.warning("monitor[%s]: 3x-ui status failed: %s", panel_id, e)

    _cached_statuses[panel_id] = (now, result)
    return result


async def collect_all_status(force: bool = False) -> list[dict]:
    """Собирает состояние всех панелей параллельно."""
    if not XUI_PANELS:
        return []
    results = await asyncio.gather(
        *(collect_status(panel, force=force) for panel in XUI_PANELS),
        return_exceptions=True,
    )
    statuses = []
    for panel, result in zip(XUI_PANELS, results):
        if isinstance(result, Exception):
            logger.warning(
                "monitor[%s]: unhandled status error: %s",
                panel.get("id"), result,
            )
            item = _new_status(panel)
            item["error"] = f"{type(result).__name__}: {result}"[:300]
            statuses.append(item)
        else:
            statuses.append(result)
    return statuses


async def save_metrics(statuses: list[dict], min_interval: int = 240) -> None:
    """Сохраняет срез метрик для графиков. Не чаще раза в 4 минуты на панель."""
    now = int(time.time())
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for status in statuses:
                if not status.get("ok"):
                    continue
                panel_id = status.get("panel_id") or "panel"
                async with db.execute(
                    "SELECT ts FROM monitor_metrics "
                    "WHERE panel_id = ? ORDER BY ts DESC LIMIT 1",
                    (panel_id,),
                ) as cur:
                    row = await cur.fetchone()
                if row and now - int(row[0]) < min_interval:
                    continue
                await db.execute(
                    "INSERT INTO monitor_metrics "
                    "(panel_id, ts, cpu_percent, mem_percent, disk_percent, "
                    "online_count, traffic_total) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        panel_id,
                        now,
                        status.get("cpu_percent"),
                        status.get("mem_percent"),
                        status.get("disk_percent"),
                        status.get("online_count"),
                        status.get("traffic_total"),
                    ),
                )
            await db.execute(
                "DELETE FROM monitor_metrics WHERE ts < ?",
                (now - 7 * 24 * 60 * 60,),
            )
            await db.commit()
    except Exception as e:
        logger.warning("monitor: metrics save failed: %s", e)


async def get_metrics_history(
    panel_id: str,
    hours: int = 24,
    limit: int = 288,
) -> list[dict]:
    """Последние точки метрик панели для графиков."""
    since = int(time.time()) - hours * 60 * 60
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT ts, cpu_percent, mem_percent, disk_percent,
                       online_count, traffic_total
                FROM (
                    SELECT ts, cpu_percent, mem_percent, disk_percent,
                           online_count, traffic_total
                    FROM monitor_metrics
                    WHERE panel_id = ? AND ts >= ?
                    ORDER BY ts DESC
                    LIMIT ?
                )
                ORDER BY ts ASC
                """,
                (panel_id, since, limit),
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]
    except Exception as e:
        logger.warning("monitor: history load failed for %s: %s", panel_id, e)
        return []


async def collect_all_status_with_history(force: bool = False) -> list[dict]:
    """Собирает статусы панелей и добавляет историю для графиков."""
    statuses = await collect_all_status(force=force)
    await save_metrics(statuses)
    for status in statuses:
        status["history"] = await get_metrics_history(status.get("panel_id") or "panel")
    return statuses


async def _state_get(key: str, default=None):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT value FROM monitor_state WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception:
        return default


async def _state_set(key: str, value):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO monitor_state(key, value, updated_at) "
                "VALUES(?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=CURRENT_TIMESTAMP",
                (key, str(value)),
            )
            await db.commit()
    except Exception as e:
        logger.warning("monitor: state update failed: %s", e)


def _state_key(panel_id, key):
    return f"{panel_id}:{key}"


async def _notify_admins(bot, text: str):
    if not bot:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, disable_notification=False)
        except Exception as e:
            logger.warning("monitor: notify %s failed: %s", admin_id, e)


async def _check_panel_health(bot, status: dict):
    """Проверяет одну панель и отправляет алерты с раздельными state-ключами."""
    panel_id = status.get("panel_id") or "panel"
    label = status.get("panel_name") or panel_id
    now = time.time()

    if not status.get("ok"):
        fails = int(await _state_get(_state_key(panel_id, "api_fail_count"), "0") or 0) + 1
        await _state_set(_state_key(panel_id, "api_fail_count"), fails)
        last_alert = float(
            await _state_get(_state_key(panel_id, "api_down_alert_ts"), "0") or 0
        )

        if fails >= API_FAIL_ALERT_AFTER and now - last_alert >= API_FAIL_COOLDOWN:
            await _notify_admins(
                bot,
                f"⚠️ 3x-ui [{label}] недоступна\n"
                f"Подряд неудачных проверок: {fails}\n"
                f"Ошибка: {status.get('error') or 'неизвестно'}\n\n"
                "Проверь панель и сервис x-ui.",
            )
            await _state_set(_state_key(panel_id, "api_down_alert_ts"), now)
        return

    # Восстановление после серии сбоев
    previous_fails = int(
        await _state_get(_state_key(panel_id, "api_fail_count"), "0") or 0
    )
    if previous_fails:
        await _state_set(_state_key(panel_id, "api_fail_count"), 0)
    last_down_alert = float(
        await _state_get(_state_key(panel_id, "api_down_alert_ts"), "0") or 0
    )
    if previous_fails >= API_FAIL_ALERT_AFTER and last_down_alert:
        await _notify_admins(
            bot,
            f"✅ 3x-ui [{label}] снова доступна. Мониторинг восстановлен.",
        )
        await _state_set(_state_key(panel_id, "api_down_alert_ts"), 0)

    metrics = [
        ("cpu", status.get("cpu_percent"), CPU_ALERT, "CPU"),
        ("mem", status.get("mem_percent"), MEM_ALERT, "RAM"),
        ("disk", status.get("disk_percent"), DISK_ALERT, "Диск"),
    ]
    for key, value, threshold, metric_label in metrics:
        if value is None or value < threshold:
            continue
        state_key = _state_key(panel_id, f"alert_{key}_ts")
        last = float(await _state_get(state_key, "0") or 0)
        if now - last < METRIC_COOLDOWN:
            continue
        await _notify_admins(
            bot,
            f"⚠️ 3x-ui [{label}]: {metric_label} {value}% (порог {threshold}%)\n"
            "Проверь нагрузку на сервер.",
        )
        await _state_set(state_key, now)

    xray_state = (status.get("xray_state") or "").lower()
    if xray_state and xray_state != "running":
        state_key = _state_key(panel_id, "alert_xray_ts")
        last = float(await _state_get(state_key, "0") or 0)
        if now - last >= XRAY_COOLDOWN:
            await _notify_admins(
                bot,
                f"⚠️ 3x-ui [{label}]: Xray не запущен "
                f"(state={status.get('xray_state')}).",
            )
            await _state_set(state_key, now)

    cert_days = status.get("cert_days_left")
    if cert_days is not None and cert_days <= CERT_ALERT_DAYS:
        state_key = _state_key(panel_id, "alert_cert_ts")
        last = float(await _state_get(state_key, "0") or 0)
        if now - last >= CERT_COOLDOWN:
            await _notify_admins(
                bot,
                f"🔐 3x-ui [{label}]: сертификат истекает через {cert_days} дн.\n"
                "Пора обновить сертификат.",
            )
            await _state_set(state_key, now)


async def check_xui_health(bot):
    """Проверка всех 3x-ui панелей по расписанию и алерты администраторам."""
    statuses = await collect_all_status(force=True)
    await save_metrics(statuses)
    for status in statuses:
        await _check_panel_health(bot, status)

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

from config import ADMIN_IDS, DB_PATH, XUI_HOST
from xui_client import XUIClient

logger = logging.getLogger(__name__)

CACHE_TTL = 15
_cached_status = None
_cached_at = 0.0

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


def _cert_info():
    """Возвращает (дней_до_окончания, ошибка) для TLS-сертификата панели."""
    try:
        parts = urlsplit(XUI_HOST or "")
        if parts.scheme != "https" or not parts.hostname:
            return None, None
        host = parts.hostname
        port = parts.port or 443
        context = ssl.create_default_context()
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


async def _get_cert_info():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _cert_info)


async def collect_status(force: bool = False) -> dict:
    """Собирает текущее состояние панели. Результат кэшируется на 15 секунд."""
    global _cached_status, _cached_at

    now = time.monotonic()
    if not force and _cached_status and now - _cached_at < CACHE_TTL:
        return _cached_status

    result = {
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

    cert_days, cert_error = await _get_cert_info()
    result["cert_days_left"] = cert_days
    result["cert_error"] = cert_error

    try:
        async with XUIClient() as xui:
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
                logger.warning("monitor: inbounds failed: %s", e)

            try:
                online = await xui.get_online_clients()
                result["online_count"] = len(online)
            except Exception as e:
                logger.warning("monitor: online clients failed: %s", e)

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:300]
        logger.warning("monitor: 3x-ui status failed: %s", e)

    _cached_status = result
    _cached_at = now
    return result


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


async def _notify_admins(bot, text: str):
    if not bot:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, disable_notification=False)
        except Exception as e:
            logger.warning("monitor: notify %s failed: %s", admin_id, e)


async def check_xui_health(bot):
    """Проверка 3x-ui по расписанию и отправка алертов администраторам."""
    status = await collect_status(force=True)
    now = time.time()

    if not status.get("ok"):
        fails = int(await _state_get("api_fail_count", "0") or 0) + 1
        await _state_set("api_fail_count", fails)
        last_alert = float(await _state_get("api_down_alert_ts", "0") or 0)

        if fails >= API_FAIL_ALERT_AFTER and now - last_alert >= API_FAIL_COOLDOWN:
            await _notify_admins(
                bot,
                "⚠️ 3x-ui недоступна\n"
                f"Подряд неудачных проверок: {fails}\n"
                f"Ошибка: {status.get('error') or 'неизвестно'}\n\n"
                "Проверь панель и сервис x-ui.",
            )
            await _state_set("api_down_alert_ts", now)
        return

    # Восстановление после серии сбоев
    previous_fails = int(await _state_get("api_fail_count", "0") or 0)
    if previous_fails:
        await _state_set("api_fail_count", 0)
    last_down_alert = float(await _state_get("api_down_alert_ts", "0") or 0)
    if previous_fails >= API_FAIL_ALERT_AFTER and last_down_alert:
        await _notify_admins(bot, "✅ 3x-ui снова доступна. Мониторинг восстановлен.")
        await _state_set("api_down_alert_ts", 0)

    metrics = [
        ("cpu", status.get("cpu_percent"), CPU_ALERT, "CPU"),
        ("mem", status.get("mem_percent"), MEM_ALERT, "RAM"),
        ("disk", status.get("disk_percent"), DISK_ALERT, "Диск"),
    ]
    for key, value, threshold, label in metrics:
        if value is None or value < threshold:
            continue
        state_key = f"alert_{key}_ts"
        last = float(await _state_get(state_key, "0") or 0)
        if now - last < METRIC_COOLDOWN:
            continue
        await _notify_admins(
            bot,
            f"⚠️ 3x-ui: {label} {value}% (порог {threshold}%)\n"
            "Проверь нагрузку на сервер.",
        )
        await _state_set(state_key, now)

    xray_state = (status.get("xray_state") or "").lower()
    if xray_state and xray_state != "running":
        last = float(await _state_get("alert_xray_ts", "0") or 0)
        if now - last >= XRAY_COOLDOWN:
            await _notify_admins(
                bot,
                f"⚠️ 3x-ui: Xray не запущен (state={status.get('xray_state')}).",
            )
            await _state_set("alert_xray_ts", now)

    cert_days = status.get("cert_days_left")
    if cert_days is not None and cert_days <= CERT_ALERT_DAYS:
        last = float(await _state_get("alert_cert_ts", "0") or 0)
        if now - last >= CERT_COOLDOWN:
            await _notify_admins(
                bot,
                f"🔐 Сертификат 3x-ui истекает через {cert_days} дн.\n"
                "Пора обновить сертификат.",
            )
            await _state_set("alert_cert_ts", now)

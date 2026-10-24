"""Сверка активных подписок в базе с клиентами 3x-ui."""

import json
import logging
import time
from datetime import datetime

import aiosqlite

from config import DB_PATH, XUI_PANELS
from database import get_state_value, set_state_value
from xui_client import XUIClient

logger = logging.getLogger(__name__)

STATE_KEY = "reconcile:last"


def _parse_db_expiry(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _panel_expiry(client):
    try:
        value = int(client.get("expiryTime") or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000)


async def _load_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT telegram_id, username, first_name, xui_email, expires_at
            FROM users WHERE status = 'active'
        """) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def _load_clients():
    clients = {}
    errors = []
    for panel in XUI_PANELS:
        try:
            async with XUIClient(panel) as xui:
                for client in await xui.get_clients():
                    email = (client.get("email") or "").strip()
                    if not email:
                        continue
                    client = dict(client)
                    client["_panel_id"] = panel.get("id")
                    clients.setdefault(email, client)
        except Exception as error:
            errors.append(f"{panel.get('name') or panel.get('id')}: {type(error).__name__}")
            logger.warning("reconcile: panel %s unavailable: %s", panel.get("id"), error)
    return clients, errors


async def _enable_client(client):
    panel_id = client.get("_panel_id")
    panel = next((p for p in XUI_PANELS if p.get("id") == panel_id), XUI_PANELS[0])
    payload = {
        "email": client.get("email"),
        "expiryTime": client.get("expiryTime", 0),
        "limitIp": client.get("limitIp", 0),
        "enable": True,
        "totalGB": client.get("totalGB", 0),
        "comment": client.get("comment", ""),
        "subId": client.get("subId", ""),
        "group": client.get("group", ""),
        "tgId": client.get("tgId", 0),
    }
    async with XUIClient(panel) as xui:
        result = await xui._post(
            f"/panel/api/clients/update/{client['email']}", payload
        )
    return bool(result.get("success"))


async def reconcile_xui(dry_run=False):
    users = await _load_active_users()
    clients, panel_errors = await _load_clients()
    active_emails = {
        (user.get("xui_email") or "").strip()
        for user in users
        if (user.get("xui_email") or "").strip()
    }

    issues = {
        "missing_email": [],
        "missing_client": [],
        "orphan_client": [],
        "expired_client": [],
        "update_failed": [],
    }
    fixed_disabled = 0
    fixed_expiry = 0

    for user in users:
        email = (user.get("xui_email") or "").strip()
        if not email:
            issues["missing_email"].append({
                "telegram_id": user["telegram_id"],
                "first_name": user.get("first_name") or "",
            })
            continue

        client = clients.get(email)
        if not client:
            issues["missing_client"].append({
                "telegram_id": user["telegram_id"],
                "email": email,
                "expires_at": user.get("expires_at"),
            })
            continue

        expiry = _panel_expiry(client)
        if expiry and expiry < datetime.now():
            issues["expired_client"].append({
                "telegram_id": user["telegram_id"],
                "email": email,
                "expires_at": expiry.strftime("%Y-%m-%d %H:%M:%S"),
            })
            continue

        if not client.get("enable", True):
            if dry_run:
                fixed_disabled += 1
            else:
                try:
                    if await _enable_client(client):
                        fixed_disabled += 1
                    else:
                        issues["update_failed"].append({
                            "telegram_id": user["telegram_id"],
                            "email": email,
                            "action": "enable",
                        })
                except Exception:
                    issues["update_failed"].append({
                        "telegram_id": user["telegram_id"],
                        "email": email,
                        "action": "enable",
                    })

        db_expiry = _parse_db_expiry(user.get("expires_at"))
        if expiry and (db_expiry is None or abs((expiry - db_expiry).total_seconds()) > 86400):
            if dry_run:
                fixed_expiry += 1
            else:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE users SET expires_at = ? WHERE telegram_id = ?",
                        (expiry.strftime("%Y-%m-%d %H:%M:%S"), user["telegram_id"]),
                    )
                    await db.commit()
                fixed_expiry += 1

    for email, client in clients.items():
        if email not in active_emails:
            issues["orphan_client"].append({
                "email": email,
                "panel": client.get("_panel_id"),
            })

    result = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": bool(dry_run),
        "active_users": len(users),
        "clients": len(clients),
        "fixed_disabled": fixed_disabled,
        "fixed_expiry": fixed_expiry,
        "issues": issues,
        "panel_errors": panel_errors,
        "ok": (
            not panel_errors
            and not issues["missing_email"]
            and not issues["missing_client"]
            and not issues["expired_client"]
            and not issues["update_failed"]
        ),
    }

    if not dry_run:
        await set_state_value(STATE_KEY, json.dumps(result, ensure_ascii=False))
        await set_state_value("reconcile:last_ts", int(time.time()))
    return result


async def get_last_reconcile():
    raw = await get_state_value(STATE_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None

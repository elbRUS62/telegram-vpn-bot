#!/usr/bin/env python3
"""Независимый монитор SkrepNet для systemd timer."""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def env(name, default=""):
    return os.environ.get(name, default).strip()


NAME = env("MONITOR_NAME", "SkrepNet")
TARGET = env("MONITOR_TARGET")
FAIL_THRESHOLD = max(1, int(env("MONITOR_FAIL_THRESHOLD", "5")))
STATE_FILE = Path(env("MONITOR_STATE", "/var/lib/skrepnet-monitor/state.json"))
INSECURE = env("MONITOR_INSECURE", "0") in ("1", "true", "yes")
ALERT_TOKEN = env("ALERT_BOT_TOKEN")
ALERT_CHAT_IDS = [
    value.strip()
    for value in env("ALERT_CHAT_IDS").split(",")
    if value.strip()
]
IGNORED_PANELS = {
    value.strip()
    for value in env("MONITOR_IGNORE_PANELS").split(",")
    if value.strip()
}
TIMEOUT = max(5, int(env("MONITOR_TIMEOUT", "15")))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "failures": 0,
            "alerted": False,
            "last_ok": None,
            "last_check": None,
        }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)


def check_health():
    if not TARGET:
        return False, "MONITOR_TARGET не задан", {}

    context = ssl._create_unverified_context() if INSECURE else ssl.create_default_context()
    request = urllib.request.Request(
        TARGET,
        headers={"User-Agent": "SkrepNet-Monitor/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, context=context, timeout=TIMEOUT) as response:
            status = response.status
            body = response.read(200_000)
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read(200_000)
    except Exception as error:
        return False, f"{type(error).__name__}: {error}", {}

    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return False, f"HTTP {status}, ответ не JSON", {}

    reasons = []
    if not (data.get("db") or {}).get("ok"):
        reasons.append("база данных")
    if not (data.get("bot") or {}).get("ok"):
        reasons.append("heartbeat бота")
    for panel in data.get("panels") or []:
        panel_id = str(panel.get("id") or "")
        if not panel.get("ok") and panel_id not in IGNORED_PANELS:
            reasons.append(f"панель {panel.get('name') or panel_id}")

    # HTTP 503 и status=degraded добавляем только если есть реальная причина.
    # Это позволяет RU-монитору игнорировать собственную панель, чтобы не
    # дублировать алерты GB-монитора.
    if reasons:
        if status != 200:
            reasons.insert(0, f"HTTP {status}")
        if data.get("status") != "ok":
            reasons.append(f"status={data.get('status')}")

    if reasons:
        return False, ", ".join(reasons), data
    return True, "ok", data


def send_alert(text):
    if not ALERT_TOKEN or not ALERT_CHAT_IDS:
        print("alert config is empty", file=sys.stderr)
        return False

    delivered = False
    for chat_id in ALERT_CHAT_IDS:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{ALERT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                if response.status == 200:
                    delivered = True
        except Exception as error:
            print(f"telegram alert failed for {chat_id}: {type(error).__name__}", file=sys.stderr)

    return delivered


def main():
    state = load_state()
    ok, reason, data = check_health()
    checked_at = now_iso()

    if ok:
        recovered = bool(state.get("alerted"))
        state.update({
            "failures": 0,
            "alerted": False,
            "last_ok": checked_at,
            "last_check": checked_at,
            "last_reason": None,
        })
        save_state(state)
        if recovered:
            send_alert(
                f"SkrepNet: {NAME} восстановлен\n"
                f"Проверка: {TARGET}\n"
                f"Время: {checked_at}"
            )
            print(f"{NAME}: recovered")
        else:
            print(f"{NAME}: ok")
        return 0

    failures = int(state.get("failures") or 0) + 1
    state.update({
        "failures": failures,
        "last_check": checked_at,
        "last_reason": reason,
    })

    print(f"{NAME}: failure {failures}/{FAIL_THRESHOLD}: {reason}")

    if failures >= FAIL_THRESHOLD and not state.get("alerted"):
        text = (
            f"SkrepNet: проблема с {NAME}\n"
            f"Проверка: {TARGET}\n"
            f"Причина: {reason}\n"
            f"Непрерывно: {failures} проверок\n"
            f"Последний успех: {state.get('last_ok') or 'неизвестно'}\n"
            f"Время: {checked_at}"
        )
        if send_alert(text):
            state["alerted"] = True
            state["alerted_at"] = checked_at
            print(f"{NAME}: alert sent")

    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

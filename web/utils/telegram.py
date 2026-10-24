"""Уведомления в Telegram из веб-процесса без импорта aiogram."""
import logging
import threading

import httpx

from config import BOT_TOKEN
from permissions import get_admin_ids

logger = logging.getLogger(__name__)


def _send(chat_id, text: str, parse_mode=None) -> bool:
    if not BOT_TOKEN or not chat_id:
        return False
    payload = {
        "chat_id": chat_id,
        "text": (text or "")[:3900],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=8,
        )
        if response.status_code != 200:
            logger.warning(
                "telegram notify failed: chat=%s status=%s",
                chat_id,
                response.status_code,
            )
            return False
        return True
    except Exception as e:
        logger.warning("telegram notify error for %s: %s", chat_id, e)
        return False


def _notify_admins(text: str, parse_mode=None):
    for admin_id in get_admin_ids():
        _send(admin_id, text, parse_mode)


def notify_admins(text: str, parse_mode=None):
    """Отправить уведомление всем администраторам в фоне."""
    if not get_admin_ids():
        return
    threading.Thread(
        target=_notify_admins,
        args=(text, parse_mode),
        daemon=True,
        name="tg-admins",
    ).start()


def notify_user(chat_id, text: str, parse_mode=None):
    """Отправить уведомление пользователю в фоне."""
    if not chat_id:
        return
    threading.Thread(
        target=_send,
        args=(chat_id, text, parse_mode),
        daemon=True,
        name="tg-user",
    ).start()

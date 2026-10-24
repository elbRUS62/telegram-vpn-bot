"""Расчёт плана и остатка дней подписки."""

import math
from datetime import datetime

from config import SUBSCRIPTION_DAYS, WEB_SUBSCRIPTION_DAYS


def plan_days_for_source(source) -> int:
    """Длительность плана: гостевая подписка короче обычной."""
    value = (source or "").strip().lower()
    return WEB_SUBSCRIPTION_DAYS if value == "web" else SUBSCRIPTION_DAYS


def days_left_from_expiry(expires_at, now=None):
    """Остаток дней с округлением вверх, чтобы первый день не терялся."""
    if not expires_at:
        return None

    if isinstance(expires_at, datetime):
        expires = expires_at
    else:
        text = str(expires_at).strip()
        try:
            expires = datetime.fromisoformat(text)
        except ValueError:
            try:
                expires = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None

    now = now or datetime.now()
    seconds = (expires - now).total_seconds()
    if seconds <= 0:
        return math.floor(seconds / 86400)
    return math.ceil(seconds / 86400)

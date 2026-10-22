import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def add_donation(username: str, amount: float, currency: str = "RUB", message: str = None):
    """Записать донат в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO donations (username, amount, currency, message)
            VALUES (?, ?, ?, ?)
        """, (username, amount, currency, message))
        await db.commit()

async def get_donations_total(currency: str = "RUB") -> float:
    """Сумма всех донатов за текущий месяц в указанной валюте."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM donations
            WHERE currency = ?
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """, (currency,)) as cur:
            row = await cur.fetchone()
            return float(row[0]) if row else 0.0

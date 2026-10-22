import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            return await cursor.fetchone()

async def get_user_by_username(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cursor:
            return await cursor.fetchone()

async def create_user_request(telegram_id: int, username: str, first_name: str,
                               xui_email: str, invited_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users
            (telegram_id, username, first_name, xui_email, status, invited_by)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (telegram_id, username, first_name, xui_email, invited_by))
        await db.commit()

async def approve_user(telegram_id: int, sub_id: str, days: int = SUBSCRIPTION_DAYS):
    expires = datetime.now() + timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET status = 'active', sub_id = ?, expires_at = ?,
            notified_3d = 0, notified_0d = 0
            WHERE telegram_id = ?
        """, (sub_id, expires, telegram_id))
        await db.commit()

async def renew_user(telegram_id: int, new_expires=None, days: int = SUBSCRIPTION_DAYS):
    if new_expires is None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT expires_at FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row and row["expires_at"]:
                current = datetime.fromisoformat(row["expires_at"])
                new_expires = max(current, datetime.now()) + timedelta(days=days)
            else:
                new_expires = datetime.now() + timedelta(days=days)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET expires_at = ?, notified_3d = 0, notified_0d = 0
            WHERE telegram_id = ?
        """, (new_expires, telegram_id))
        await db.commit()
        return new_expires

async def get_expiring_users(days: int):
    target_date = (datetime.now() + timedelta(days=days)).date()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND DATE(expires_at) = ?
            AND notified_3d = 0
        """, (target_date,)) as cursor:
            return await cursor.fetchall()

async def get_expired_today():
    today = datetime.now().date()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND DATE(expires_at) = ?
            AND notified_0d = 0
        """, (today,)) as cursor:
            return await cursor.fetchall()

async def mark_notified(telegram_id: int, field: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = 1 WHERE telegram_id = ?", (telegram_id,))
        await db.commit()

async def increment_invites(inviter_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET invites_count = invites_count + 1
            WHERE telegram_id = ?
        """, (inviter_id,))
        await db.commit()

async def delete_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()

async def get_inactive_users(days: int = 30) -> list:
    """Пользователи, у которых подписка истекла более N дней назад."""
    cutoff = datetime.now() - timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND expires_at < ?
        """, (cutoff,)) as cur:
            return await cur.fetchall()

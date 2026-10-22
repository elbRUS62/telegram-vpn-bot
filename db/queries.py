import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def get_users_paginated(statuses: list, offset: int = 0, limit: int = 10) -> list:
    """Получить пользователей с определёнными статусами, с пагинацией.

    Args:
        statuses: список статусов, например ['active', 'pending']
        offset: сколько пропустить
        limit: сколько вернуть
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(statuses))
        async with db.execute(f"""
            SELECT * FROM users
            WHERE status IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (*statuses, limit, offset)) as cur:
            return await cur.fetchall()

async def count_users_by_statuses(statuses: list) -> int:
    """Сколько пользователей с указанными статусами.

    Args:
        statuses: список статусов, например ['active', 'pending']
    """
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" * len(statuses))
        async with db.execute(f"""
            SELECT COUNT(*) FROM users WHERE status IN ({placeholders})
        """, statuses) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def count_active_users() -> int:
    """Сколько пользователей со статусом 'active'."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE status = 'active'"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def is_limit_reached(max_users: int) -> bool:
    """Достигнут ли лимит активных пользователей."""
    if max_users <= 0:
        return False
    count = await count_active_users()
    return count >= max_users

async def increment_renew_count(telegram_id: int) -> int:
    """Увеличить счётчик продлений. Возвращает новое значение."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET renew_count = COALESCE(renew_count, 0) + 1
            WHERE telegram_id = ?
        """, (telegram_id,))
        await db.commit()

        async with db.execute(
            "SELECT renew_count FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

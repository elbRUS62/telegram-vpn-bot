import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def add_to_waitlist(telegram_id: int, username: str, first_name: str) -> bool:
    """Добавить в лист ожидания. Возвращает True, если добавлен, False, если уже был."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO waitlist (telegram_id, username, first_name)
                VALUES (?, ?, ?)
            """, (telegram_id, username, first_name))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_waitlist_position(telegram_id: int) -> int | None:
    """Позиция в очереди (1-based) или None, если не в очереди."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM waitlist
            WHERE id <= (SELECT id FROM waitlist WHERE telegram_id = ?)
        """, (telegram_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] > 0 else None

async def get_waitlist_count() -> int:
    """Сколько человек в листе ожидания."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM waitlist") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def pop_from_waitlist() -> dict | None:
    """Взять первого из очереди и удалить его из waitlist.
    Возвращает данные пользователя или None, если очередь пуста."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM waitlist ORDER BY id ASC LIMIT 1
        """) as cur:
            row = await cur.fetchone()

        if not row:
            return None

        await db.execute("DELETE FROM waitlist WHERE id = ?", (row["id"],))
        await db.commit()
        return dict(row)

async def is_in_waitlist(telegram_id: int) -> bool:
    """Есть ли пользователь в листе ожидания."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM waitlist WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            return await cur.fetchone() is not None

async def clear_old_waitlist(days: int = 30):
    """Удалить из листа ожидания тех, кто ждёт больше N дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM waitlist
            WHERE created_at < datetime('now', ?)
        """, (f'-{days} days',))
        await db.commit()

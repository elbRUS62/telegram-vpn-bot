import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def get_support_unread_count(telegram_id: int) -> int:
    """Количество тикетов с непрочитанным ответом для пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM support_tickets "
            "WHERE telegram_id = ? AND unread_user = 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0] or 0) if row else 0

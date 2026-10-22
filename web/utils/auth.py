"""Валидация initData от Telegram WebApp."""

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

import aiosqlite

from config import BOT_TOKEN, DB_PATH

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str) -> dict | None:
    """Проверить подпись initData. Возвращает dict с данными user или None."""
    if not init_data:
        logger.warning("init_data пустой!")
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_value = parsed.pop("hash", "")
        if not hash_value:
            return None
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if calculated_hash != hash_value:
            return None
        user_data = json.loads(parsed.get("user", "{}"))

        # Обновляем last_seen для «онлайн» в админке
        tg_id = user_data.get("id")
        if tg_id:
            try:
                _update_last_seen(tg_id)
            except Exception:
                logger.exception("Не удалось обновить last_seen для %s", tg_id)

        return user_data
    except Exception:
        logger.exception("initData validation error")
        return None

def _update_last_seen(tg_id: int):
    """Обновить last_seen пользователя (для индикатора «онлайн»)."""
    from web.utils.async_helper import run_async
    from datetime import datetime

    async def _upd():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET last_seen = ? WHERE telegram_id = ?",
                (datetime.now(), tg_id),
            )
            await db.commit()

    run_async(_upd())


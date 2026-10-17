"""Валидация initData от Telegram WebApp."""

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

from config import BOT_TOKEN

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str) -> dict | None:
    """Проверить подпись initData. Возвращает dict с данными user или None."""
    if not init_data:
        logger.warning("init_data пустой!")
        return None
    logger.info(f"RAW init_data: {init_data[:100]}...")
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
        return json.loads(parsed.get("user", "{}"))
    except Exception as e:
        logger.error(f"initData validation error: {e}")
        return None

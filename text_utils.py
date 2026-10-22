"""Лёгкие утилиты без тяжёлых зависимостей.

Вынесено из handlers/utils.py: веб-части нельзя импортировать пакет
handlers, потому что его __init__ тянет aiogram и все хендлеры
(это ~200 МБ RSS на каждый воркер gunicorn).
"""

import re


def sanitize_email(username: str, telegram_id: int) -> str:
    """Формирует email для 3x-ui.
    Приоритет: username (если есть) → user{telegram_id}."""
    if username:
        # Telegram username всегда латиница, цифры и _
        cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', username)
        if cleaned:
            return cleaned[:32]

    # Нет username или после очистки пусто — используем ID
    return f"user{telegram_id}"

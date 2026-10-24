"""Обновить имена и аватарки пользователей из Telegram."""

import asyncio

from web.utils.avatars import refresh_user_avatars


if __name__ == "__main__":
    asyncio.run(refresh_user_avatars())

"""Уведомление следующего из листа ожидания при освобождении места."""

import logging

from aiogram import Bot

from config import MAX_USERS
from database import (
    pop_from_waitlist, get_waitlist_count, is_limit_reached,
    clear_old_waitlist,
)

logger = logging.getLogger(__name__)


async def notify_next_in_queue(bot: Bot) -> bool:
    """Взять первого из листа ожидания и уведомить его.
    Возвращает True, если кого-то уведомили.
    """
    if await is_limit_reached(MAX_USERS):
        logger.info("?? Места нет, лист ожидания не трогаем")
        return False

    count = await get_waitlist_count()
    if count == 0:
        logger.info("?? Лист ожидания пуст")
        return False

    user_data = await pop_from_waitlist()
    if not user_data:
        return False

    telegram_id = user_data["telegram_id"]
    first_name = user_data.get("first_name") or "друг"

    try:
        await bot.send_message(
            telegram_id,
            f"?? <b>Освободилось место!</b>\n\n"
            f"Привет, {first_name}!\n\n"
            f"Ты был в листе ожидания — и вот твоя очередь подошла.\n\n"
            f"Нажми «?? Получить подписку» в главном меню, "
            f"чтобы получить VPN.",
            parse_mode="HTML"
        )
        logger.info(f"? Уведомлён {telegram_id} ({first_name}) из листа ожидания")
        return True
    except Exception as e:
        logger.error("? Не удалось уведомить {telegram_id}: ")
        return False


async def cleanup_waitlist():
    """Удалить из листа ожидания тех, кто ждёт больше 30 дней."""
    await clear_old_waitlist(days=30)
    logger.info("?? Лист ожидания очищен от старых записей")
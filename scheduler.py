from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
import logging
import aiosqlite

from database import (
    get_expiring_users, get_expired_today, mark_notified,
    get_inactive_users, delete_user,
    get_abandoned_web_invites,
)
from keyboards import renew_keyboard
from xui_client import XUIClient
from config import ADMIN_ID, DB_PATH
from handlers.progress import render_progress
from handlers.waitlist import notify_next_in_queue, cleanup_waitlist

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def setup_scheduler(bot: Bot):
    # Напоминания о продлении — каждый день в 10:00
    scheduler.add_job(
        check_subscriptions,
        "cron",
        hour=10,
        minute=0,
        args=[bot],
        id="check_subscriptions"
    )

    # Автоочистка неактивных — каждый день в 4:00
    scheduler.add_job(
        cleanup_inactive_users,
        "cron",
        hour=4,
        minute=0,
        args=[bot],
        id="cleanup_inactive_users"
    )

    # Очистка листа ожидания — 1-го числа каждого месяца в 3:30
    scheduler.add_job(
        cleanup_waitlist,
        "cron",
        day=1,
        hour=3,
        minute=30,
        id="cleanup_waitlist"
    )

    # Автоочистка «брошенных» веб-выдач — каждый день в 5:00
    scheduler.add_job(
        cleanup_abandoned_web_invites,
        "cron",
        hour=5,
        minute=0,
        args=[bot],
        id="cleanup_abandoned_web_invites"
    )

    scheduler.start()


async def check_subscriptions(bot: Bot):
    """Напоминания за 3 дня и в день окончания. НЕ продлеваем автоматически."""

    # За 3 дня
    for user in await get_expiring_users(3):
        try:
            progress_line = await render_progress(short=True)

            await bot.send_message(
                user["telegram_id"],
                f"⏳ Твоя подписка истекает через 3 дня.\n"
                f"Продли, чтобы не остаться без VPN.\n\n"
                f"{progress_line}",
                reply_markup=renew_keyboard(),
                disable_notification=True
            )
            await mark_notified(user["telegram_id"], "notified_3d")
        except Exception:
            pass

    # В день окончания
    for user in await get_expired_today():
        try:
            progress_line = await render_progress(short=True)

            await bot.send_message(
                user["telegram_id"],
                f"🔔 Сегодня последний день подписки!\n"
                f"После полуночи доступ отключится.\n\n"
                f"{progress_line}",
                reply_markup=renew_keyboard(),
                disable_notification=True
            )
            await mark_notified(user["telegram_id"], "notified_0d")
        except Exception as e:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"Ошибка напоминания для {user['xui_email']}"
                )
            except Exception:
                pass


async def cleanup_inactive_users(bot: Bot):
    """Удаляет пользователей, у которых подписка истекла более 30 дней назад."""
    users = await get_inactive_users(days=30)

    if not users:
        return

    deleted = 0
    for user in users:
        try:
            async with XUIClient() as xui:
                try:
                    await xui._post(f"/panel/api/clients/del/{user['xui_email']}")
                except Exception:
                    pass

            await delete_user(user["telegram_id"])
            deleted += 1
        except Exception as e:
            logger.error(f"Ошибка удаления {user['xui_email']}")

    if deleted:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🗑 Автоочистка: удалено {deleted} неактивных пользователей "
                f"(подписка истекла 30+ дней назад).",
                disable_notification=True
            )
        except Exception:
            pass

        await notify_next_in_queue(bot)


async def cleanup_abandoned_web_invites(bot: Bot):
    """Удаляет «брошенные» веб-выдачи:
      - активированы на сайте (is_used=1, counted=1)
      - НЕ привязаны к боту (bound_to_tg_id IS NULL)
      - прошло 30+ дней с активации

    Удаляет клиентов из 3x-ui и записи из invite_links.
    """
    links = await get_abandoned_web_invites(days=30)

    if not links:
        logger.info("🧹 Брошенных веб-выдач нет")
        return

    deleted = 0
    for link in links:
        try:
            # Удаляем клиента из 3x-ui
            async with XUIClient() as xui:
                try:
                    await xui.delete_client(link["xui_email"])
                except Exception as e:
                    logger.warning(f"Не удалось удалить клиента {link['xui_email']}")

            # Удаляем запись из invite_links
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM invite_links WHERE token = ?",
                    (link["token"],)
                )
                await db.commit()

            deleted += 1
            logger.info(f"🗑 Удалена брошенная веб-выдача: {link['xui_email']}")
        except Exception as e:
            logger.error(f"Ошибка удаления {link['xui_email']}")

    if deleted:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🧹 <b>Автоочистка веб-выдач</b>\n\n"
                f"Удалено брошенных: <b>{deleted}</b>\n"
                f"(активированы 30+ дней назад, но не привязаны к боту)",
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception:
            pass
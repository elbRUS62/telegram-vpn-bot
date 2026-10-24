from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from datetime import datetime, timedelta
from html import escape
import logging
import time
import aiosqlite

from monitoring import check_xui_health
from reconciliation import reconcile_xui
from database import (
    get_expiring_users, get_expired_today, mark_notified,
    get_inactive_users, delete_user,
    get_abandoned_web_invites, get_expired_web_guests,
    get_state_value, set_state_value,
)
from keyboards import renew_keyboard
from xui_client import XUIClient
from config import DB_PATH
from permissions import get_admin_ids
from handlers.progress import render_progress
from handlers.waitlist import notify_next_in_queue, cleanup_waitlist

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def setup_scheduler(bot: Bot):
    # Heartbeat бота для /health
    scheduler.add_job(
        update_bot_heartbeat,
        "interval",
        minutes=1,
        id="bot_heartbeat",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )

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

    # Удаление гостевых веб-подписок после 3 дней — каждый час
    scheduler.add_job(
        cleanup_expired_web_guests,
        "interval",
        hours=1,
        args=[bot],
        id="cleanup_expired_web_guests",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(minutes=2),
    )

    # Напоминание о тикетах без ответа — каждые 6 часов
    scheduler.add_job(
        remind_stale_tickets,
        "interval",
        hours=6,
        args=[bot],
        id="remind_stale_tickets",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(minutes=5),
    )

    # Мониторинг 3x-ui — каждые 5 минут, первый запуск через 30 секунд
    scheduler.add_job(
        check_xui_health,
        "interval",
        minutes=5,
        args=[bot],
        id="check_xui_health",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=30),
    )

    # Сверка пользователей и клиентов 3x-ui — каждые 30 минут
    scheduler.add_job(
        reconcile_xui,
        "interval",
        minutes=30,
        id="reconcile_xui",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(minutes=2),
    )

    scheduler.start()


async def update_bot_heartbeat():
    await set_state_value("bot:heartbeat", int(time.time()))


async def remind_stale_tickets(bot: Bot):
    """Напоминает админам о тикетах, ожидающих ответа больше суток."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, subject, updated_at
                   FROM support_tickets
                   WHERE status IN ('open', 'answered')
                     AND unread_admin = 1
                     AND COALESCE(updated_at, created_at) <= datetime('now','-24 hours')
                   ORDER BY COALESCE(updated_at, created_at) ASC
                   LIMIT 20"""
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            return
        now = int(time.time())
        last = await get_state_value("tickets:stale_reminder")
        try:
            if last and now - int(last) < 12 * 60 * 60:
                return
        except (TypeError, ValueError):
            pass
        lines = [f"#{row['id']} · {escape(str(row['subject'] or '')[:80])}" for row in rows]
        text = (
            f"<b>Тикеты без ответа больше 24 часов: {len(rows)}</b>\n\n"
            + "\n".join(lines)
        )
        for admin_id in get_admin_ids():
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception:
                logger.warning("Не удалось отправить напоминание о тикетах админу %s", admin_id)
        await set_state_value("tickets:stale_reminder", now)
    except Exception:
        logger.exception("Ошибка напоминания о тикетах")


async def check_subscriptions(bot: Bot):
    """Напоминания за 3 дня и в день окончания. НЕ продлеваем автоматически."""

    # За 3 дня
    for user in await get_expiring_users(3):
        try:
            progress_line = await render_progress(short=True)

            await bot.send_message(
                user["telegram_id"],
                f"<b>Подписка истекает через 3 дня</b>\n"
                f"Продли подписку, чтобы не потерять доступ к VPN.\n\n"
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
                f"<b>Подписка истекает сегодня</b>\n\n"
                f"После полуночи доступ к VPN отключится. "
                f"Продли подписку, чтобы сохранить доступ.\n\n"
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
                f"Автоочистка: удалено {deleted} неактивных пользователей "
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
        logger.info("Брошенных веб-выдач нет")
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
            logger.info(f"Удалена брошенная веб-выдача: {link['xui_email']}")
        except Exception as e:
            logger.error(f"Ошибка удаления {link['xui_email']}")

    if deleted:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"<b>Автоочистка веб-выдач</b>\n\n"
                f"Удалено брошенных: <b>{deleted}</b>\n"
                f"(активированы 30+ дней назад, но не привязаны к боту)",
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception:
            pass


async def cleanup_expired_web_guests(bot: Bot):
    """Удаляет гостевые веб-подписки после истечения 3 дней."""
    guests = await get_expired_web_guests()
    if not guests:
        return

    deleted = 0
    for guest in guests:
        email = guest.get("xui_email")
        if not email:
            continue
        try:
            async with XUIClient() as xui:
                try:
                    await xui.delete_client(email)
                except Exception:
                    logger.warning("Не удалось удалить гостевого клиента %s", email)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM users WHERE xui_email = ? AND source = 'web'"
                    " AND (telegram_id IS NULL OR telegram_id = 0)",
                    (email,),
                )
                await db.execute(
                    "DELETE FROM invite_links WHERE xui_email = ? "
                    " AND bound_to_tg_id IS NULL",
                    (email,),
                )
                await db.commit()

            deleted += 1
            logger.info("Удалена гостевая веб-подписка: %s", email)
        except Exception:
            logger.exception("Ошибка удаления гостевой веб-подписки %s", email)

    if deleted:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"Автоочистка гостевых подписок: удалено {deleted}.",
                disable_notification=True,
            )
        except Exception:
            pass
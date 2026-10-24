import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from config import BOT_TOKEN, BOT_NAME, BOT_VERSION
from handlers import router
from scheduler import setup_scheduler
from database import init_db, set_state_value
from donation_socket import start_donation_socket
from observability import capture_exception, init_sentry
from permissions import get_admin_ids

logging.basicConfig(level=logging.INFO)
init_sentry("bot")

async def main():
    logging.info(f"🚀 {BOT_NAME} v{BOT_VERSION} запускается...")
    await init_db()
    await set_state_value("bot:heartbeat", int(time.time()))

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    @dp.errors()
    async def on_error(event: ErrorEvent):
        logging.error("Ошибка обработки обновления", exc_info=event.exception)
        capture_exception(event.exception)
        return True

    setup_scheduler(bot)

    # Запускаем DonationAlerts WebSocket в фоне
    da_token = os.getenv("DONATION_ALERTS_TOKEN", "")
    if da_token:
        asyncio.create_task(start_donation_socket(bot, get_admin_ids(), da_token))
        logging.info("✅ DonationAlerts Socket запущен в фоне")
    else:
        logging.warning("⚠️ DONATION_ALERTS_TOKEN не задан — сокет не запущен")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
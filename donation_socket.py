import asyncio
import json
import logging
import websockets
import httpx
from aiogram import Bot

logger = logging.getLogger(__name__)


class DonationAlertsCentrifugo:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.bot = None
        self.admin_ids = []
        self.user_id = None
        self.socket_token = None
        self.centrifugo_url = "wss://centrifugo.donationalerts.com/connection/websocket"
        self.api_base = "https://www.donationalerts.com/api/v1"
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _get_user_info(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/user/oauth", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()["data"]
            self.user_id = data["id"]
            self.socket_token = data["socket_connection_token"]
            logger.info(f"Получен user_id: {self.user_id}")

    async def _subscribe_to_channel(self, ws, client_id: str):
        channel = f"$alerts:donation_{self.user_id}"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/centrifuge/subscribe",
                headers=self.headers,
                json={"channels": [channel], "client": client_id}
            )
            resp.raise_for_status()
            sub_data = resp.json()

            if "channels" not in sub_data:
                raise Exception(f"Нет channels: {sub_data}")

            channel_token = sub_data["channels"][0]["token"]

        await ws.send(json.dumps({
            "params": {"channel": channel, "token": channel_token},
            "method": 1,
            "id": 2
        }))
        logger.info(f"Подписка на канал: {channel}")

    async def _handle_donation(self, data: dict):
        try:
            logger.info(f"Донат data: {data}")
            username = data.get("username") or "Аноним"
            amount = data.get("amount", 0)
            currency = data.get("currency", "RUB")
            message = data.get("message", "")

            currency_emoji = {
                "RUB": "₽",
                "USD": "$",
                "EUR": "€",
                "BYN": "Br",
                "KZT": "₸",
                "UAH": "₴",
            }.get(currency, currency)

            logger.info(f"Новый донат: {username} - {amount} {currency}")

            # Записываем донат в БД
            try:
                from database import add_donation
                await add_donation(
                    username=username,
                    amount=float(amount),
                    currency=currency,
                    message=message or None
                )
                logger.info(f"✅ Донат записан в БД: {username} - {amount} {currency}")
            except Exception as e:
                logger.error("❌ Ошибка записи доната в БД: ")

            text = (
                f"💰 <b>Новый донат!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>От:</b> {username}\n"
                f"💵 <b>Сумма:</b> <code>{amount} {currency_emoji}</code>\n"
            )

            if message:
                text += f"\n💬 <b>Сообщение:</b>\n<i>{message}</i>"

            for admin_id in self.admin_ids:
                try:
                    result = await self.bot.send_message(
                        admin_id,
                        text,
                        parse_mode="HTML",
                        disable_notification=True
                    )
                    logger.info(f"✅ Отправлено админу {admin_id}: message_id={result.message_id}")
                except Exception:
                    logger.exception("Ошибка отправки админу %s", admin_id)

        except Exception:
            logger.exception("Ошибка обработки доната")

    async def start(self, bot: Bot, admin_ids: list):
        self.bot = bot
        self.admin_ids = admin_ids

        await self._get_user_info()

        async with websockets.connect(self.centrifugo_url) as ws:
            logger.info("Подключен к Centrifugo WebSocket")

            await ws.send(json.dumps({
                "params": {"token": self.socket_token},
                "id": 1
            }))

            auth_response = json.loads(await ws.recv())
            client_id = auth_response["result"]["client"]
            logger.info(f"Авторизован. Client ID: {client_id}")

            await self._subscribe_to_channel(ws, client_id)

            async for message in ws:
                try:
                    # Centrifugo может присылать несколько JSON через \n
                    for line in message.strip().split("\n"):
                        if not line.strip():
                            continue

                        data = json.loads(line)

                        result = data.get("result", {})
                        channel = result.get("channel", "")
                        if not channel.startswith("$alerts:donation_"):
                            continue

                        inner_data = result.get("data", {})
                        if "data" not in inner_data:
                            continue

                        donation = inner_data["data"]
                        await self._handle_donation(donation)

                except Exception as e:
                    logger.error("Ошибка обработки сообщения: ")


async def _notify_admins(bot: Bot, admin_ids: list, text: str):
    """Отправить уведомление всем админам (тихое)."""
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception:
            logger.exception("Не удалось уведомить админа %s", admin_id)


async def start_donation_socket(bot: Bot, admin_ids: list, token: str):
    if not token:
        logger.warning("DONATION_ALERTS_TOKEN не задан")
        return

    client = DonationAlertsCentrifugo(token)

    was_connected = False
    first_attempt = True
    attempt = 0

    while True:
        attempt += 1
        try:
            logger.info(f"🔄 Centrifugo: попытка #{attempt}")
            await client.start(bot, admin_ids)

            # Сюда попадаем, если start() завершился без исключения
            if not was_connected:
                was_connected = True
                attempt = 0

                if not first_attempt:
                    await _notify_admins(
                        bot, admin_ids,
                        "✅ <b>Centrifugo DonationAlerts восстановлен</b>\n\n"
                        "Подключение к WebSocket восстановлено. "
                        "Уведомления о донатах снова работают."
                    )
            first_attempt = False

        except Exception as e:
            err_msg = "Внутренняя ошибка"
            logger.error(f"❌ Ошибка Centrifugo: {err_msg}")

            if was_connected:
                was_connected = False
                await _notify_admins(
                    bot, admin_ids,
                    "⚠️ <b>Centrifugo DonationAlerts недоступен</b>\n\n"
                    f"<code>{err_msg}</code>\n\n"
                    "Уведомления о донатах временно не работают. "
                    "Донаты через Telegram Stars продолжают работать.\n\n"
                    "Бот попробует переподключиться автоматически."
                )
            elif first_attempt:
                logger.warning(
                    "⚠️ Centrifugo недоступен при старте бота — "
                    "уведомление админам не отправлено"
                )

            first_attempt = False

        # Экспоненциальная задержка: 10, 20, 40, 80, 160, 300, 300... сек
        delay = min(10 * (2 ** min(attempt - 1, 5)), 300)
        logger.info(f"⏳ Следующая попытка Centrifugo через {delay} сек")
        await asyncio.sleep(delay)
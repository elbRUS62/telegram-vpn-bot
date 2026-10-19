import hashlib
import aiohttp
import logging
from datetime import datetime, timedelta

from config import (
    XUI_HOST, XUI_BASE_PATH, XUI_API_TOKEN,
    INBOUND_GB, LIMIT_IP, SUBSCRIPTION_DAYS,
    SUB_BASE_URL, SUB_PATH, BOT_NAME
)

logger = logging.getLogger(__name__)


class XUIClient:
    def __init__(self):
        self.base_url = f"{XUI_HOST}{XUI_BASE_PATH}"
        self.session = None
        self.headers = {
            "Authorization": f"Bearer {XUI_API_TOKEN}",
            "Content-Type": "application/json"
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _post(self, path: str, data: dict = None):
        url = f"{self.base_url}{path}"
        async with self.session.post(url, json=data) as resp:
            if resp.status == 401:
                raise Exception("Unauthorized: API token is invalid or expired")
            return await resp.json()

    async def _get(self, path: str):
        url = f"{self.base_url}{path}"
        async with self.session.get(url) as resp:
            if resp.status == 401:
                raise Exception("Unauthorized: API token is invalid or expired")
            return await resp.json()

    async def add_client(
        self,
        email: str,
        days: int = None,
        comment: str = None,
        tg_id: int = 0,
    ) -> str:
        """Создать клиента в 3x-ui и добавить в группу BOT_NAME.

        Args:
            email: email клиента (используется как имя)
            days: срок подписки в днях
            comment: комментарий для панели 3x-ui (человекочитаемый)
            tg_id: Telegram ID пользователя (для фильтрации в 3x-ui)
        """
        if days is None:
            days = SUBSCRIPTION_DAYS
        expires_ms = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)

        # Генерируем subId из email — гарантированно уникальный
        sub_id = hashlib.sha256(email.encode()).hexdigest()[:16]

        payload = {
            "client": {
                "email": email,
                "enable": True,
                "expiryTime": expires_ms,
                "limitIp": LIMIT_IP,
                "totalGB": 0,
                "tgId": tg_id,
                "subId": sub_id,
                "comment": comment or ""
            },
            "inboundIds": [INBOUND_GB]
        }
        result = await self._post("/panel/api/clients/add", payload)
        if not result.get("success"):
            raise Exception(f"Add client failed: {result}")

        # Добавляем в группу с именем бота (BOT_NAME)
        try:
            await self._post("/panel/api/clients/groups/bulkAdd", {
                "emails": [email],
                "group": BOT_NAME
            })
            logger.info(f"✅ {email} добавлен в группу {BOT_NAME}")
        except Exception as e:
            logger.warning("⚠️ Не удалось добавить {email} в группу {BOT_NAME}: ")

        return sub_id

    async def get_client(self, email: str) -> dict:
        """Получить данные клиента, включая subId.
        Возвращает вложенный объект client (как ожидает остальной код)."""
        result = await self._get(f"/panel/api/clients/get/{email}")
        if not result.get("success"):
            raise Exception(f"Get client failed: {result}")
        obj = result["obj"]
        return obj.get("client", obj)

    async def update_tg_id(self, email: str, tg_id: int) -> bool:
        """Обновить только поле tgId у клиента (не трогая остальные)."""
        try:
            client = await self.get_client(email)
        except Exception:
            return False

        payload = {
            "email": email,
            "expiryTime": client.get("expiryTime", 0),
            "limitIp": client.get("limitIp", LIMIT_IP),
            "enable": client.get("enable", True),
            "totalGB": client.get("totalGB", 0),
            "comment": client.get("comment", ""),
            "subId": client.get("subId", ""),
            "group": client.get("group", ""),
            "tgId": tg_id,
        }
        result = await self._post(f"/panel/api/clients/update/{email}", payload)
        return result.get("success", False)

    async def update_expiry(self, email: str, days: int = SUBSCRIPTION_DAYS):
        """Продлить подписку."""
        client = await self.get_client(email)
        current_expiry = client.get("expiryTime", 0)
        if current_expiry and current_expiry > 0:
            current_dt = datetime.fromtimestamp(current_expiry / 1000)
            new_expiry = max(current_dt, datetime.now()) + timedelta(days=days)
        else:
            new_expiry = datetime.now() + timedelta(days=days)
        expires_ms = int(new_expiry.timestamp() * 1000)
        payload = {
            "email": email,
            "expiryTime": expires_ms,
            "limitIp": LIMIT_IP,
            "enable": True,
            "totalGB": 0
        }
        result = await self._post(f"/panel/api/clients/update/{email}", payload)
        if not result.get("success"):
            raise Exception(f"Update failed: {result}")
        return new_expiry

    async def update_comment(self, email: str, comment: str) -> bool:
        """Обновить только поле comment (не трогая остальные)."""
        try:
            client = await self.get_client(email)
        except Exception:
            return False

        payload = {
            "email": email,
            "expiryTime": client.get("expiryTime", 0),
            "limitIp": client.get("limitIp", LIMIT_IP),
            "enable": client.get("enable", True),
            "totalGB": client.get("totalGB", 0),
            "comment": comment,
            "subId": client.get("subId", ""),
            "group": client.get("group", ""),
            "tgId": client.get("tgId", 0),
        }
        result = await self._post(f"/panel/api/clients/update/{email}", payload)
        return result.get("success", False)

    async def delete_client(self, email: str) -> bool:
        """Удалить клиента из 3x-ui по email."""
        result = await self._post(f"/panel/api/clients/del/{email}")
        return result.get("success", False)

    def build_sub_url(self, sub_id: str) -> str:
        """Собрать ссылку на подписку."""
        return f"{SUB_BASE_URL}{SUB_PATH}{sub_id}"
    async def is_client_online(self, email: str) -> bool:
        """Проверяет, онлайн ли клиент (только через список onlines)."""
        try:
            result = await self._post("/panel/api/clients/onlines")
            obj = result.get("obj", [])
            if result.get("success") and isinstance(obj, list):
                return email in obj
        except Exception as e:
            logger.error("is_client_online error: ")
        return False
    async def get_client_traffic(self, email: str) -> dict:
        """Получить трафик клиента (up/down в байтах) через /panel/api/clients/traffic/{email}."""
        try:
            result = await self._get(f"/panel/api/clients/traffic/{email}")
            if result.get("success"):
                return result.get("obj", {})
            logger.warning(f"get_client_traffic: success=False для {email}: {result}")
        except Exception as e:
            logger.error("get_client_traffic error для {email}: ")
        return {}

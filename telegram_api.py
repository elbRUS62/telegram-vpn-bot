"""Тонкий HTTP-клиент Telegram Bot API для веб-части.

aiogram нужен только боту: сайту хватает нескольких методов, а импорт
aiogram в веб-процессе стоит ~200 МБ RSS и тянет весь пакет handlers.
Токен никогда не попадает в логи (в URL он есть, но логируем только метод).
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def _call(client: httpx.AsyncClient, token: str, method: str, params: dict):
    url = _API_URL.format(token=token, method=method)
    try:
        resp = await client.post(url, json=params)
    except httpx.HTTPError:
        logger.exception("Telegram API %s: запрос не выполнен", method)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "Telegram API %s: ответ не JSON (HTTP %s)", method, resp.status_code
        )
        return None

    if not data.get("ok"):
        logger.error(
            "Telegram API %s: %s (HTTP %s)",
            method,
            data.get("description", "unknown error"),
            resp.status_code,
        )
        return None

    return data.get("result")


async def call(token: str, method: str, **params):
    """Вызывает метод Bot API. Возвращает result или None при ошибке."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await _call(client, token, method, params)


class Telegram:
    """Переиспользуемый клиент — для рассылок (одно соединение на пачку)."""

    def __init__(self, token: str):
        self._token = token
        self._client = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()

    async def call(self, method: str, **params):
        return await _call(self._client, self._token, method, params)

    async def send_message(self, chat_id, text, **extra):
        return await self.call("sendMessage", chat_id=chat_id, text=text, **extra)

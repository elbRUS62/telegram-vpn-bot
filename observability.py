"""Отправка ошибок в Sentry или GlitchTip.

Интеграция необязательная: если `SENTRY_DSN` не задан, все функции
работают как заглушки и ничего не отправляют.

Перед отправкой события очищаются от Telegram initData, токенов,
куки и заголовков, чтобы в трекер не попадали персональные данные.
"""

import logging
import re
from typing import Any, Optional

import sentry_sdk
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from config import (
    BOT_VERSION,
    SENTRY_DSN,
    SENTRY_ENVIRONMENT,
    SENTRY_TRACES_RATE,
)

logger = logging.getLogger(__name__)

_initialized = False

# Токен бота в URL вида /bot123456:AA.../method
_BOT_TOKEN_RE = re.compile(r"/bot\d+:[A-Za-z0-9_-]+", re.IGNORECASE)
# Секретные параметры в строках запроса
_SECRET_QUERY_RE = re.compile(
    r"((?:init_data|initdata|token|password|secret|authorization|csrf_token|hash)"
    r"=)[^&\s\"']+",
    re.IGNORECASE,
)
_SENSITIVE_KEYS = (
    "init_data",
    "initdata",
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
    "csrf",
    "session",
    "api_key",
    "hash",
)


def _scrub_text(value: str) -> str:
    value = _BOT_TOKEN_RE.sub("/bot<token>", value)
    return _SECRET_QUERY_RE.sub(r"\1[Filtered]", value)


def _scrub_mapping(data: Any) -> None:
    if not isinstance(data, dict):
        return
    for key in list(data.keys()):
        lowered = str(key).lower()
        value = data[key]
        if any(marker in lowered for marker in _SENSITIVE_KEYS):
            data[key] = "[Filtered]"
        elif isinstance(value, str):
            data[key] = _scrub_text(value)
        elif isinstance(value, dict):
            _scrub_mapping(value)
        elif isinstance(value, list):
            _scrub_list(value)


def _scrub_list(values: Any) -> None:
    if not isinstance(values, list):
        return
    for index, value in enumerate(values):
        if isinstance(value, str):
            values[index] = _scrub_text(value)
        elif isinstance(value, dict):
            _scrub_mapping(value)
        elif isinstance(value, list):
            _scrub_list(value)


def scrub_event(event: dict, hint: Optional[dict] = None) -> dict:
    """Убирает персональные данные и секреты из события перед отправкой."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "headers", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = _scrub_text(request["url"])

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        for breadcrumb in breadcrumbs.get("values") or []:
            if not isinstance(breadcrumb, dict):
                continue
            if isinstance(breadcrumb.get("message"), str):
                breadcrumb["message"] = _scrub_text(breadcrumb["message"])
            data = breadcrumb.get("data")
            if isinstance(data, dict):
                data.pop("headers", None)
                data.pop("cookies", None)
                _scrub_mapping(data)

    _scrub_mapping(event.get("extra"))
    _scrub_mapping(event.get("contexts"))
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("ip_address", None)
        user.pop("email", None)
        user.pop("username", None)
    return event


def init_sentry(component: str, dsn: Optional[str] = None) -> bool:
    """Включает Sentry для компонента bot/web. Без DSN ничего не делает."""
    global _initialized

    target_dsn = (SENTRY_DSN if dsn is None else dsn) or ""
    if not target_dsn.strip() or _initialized:
        return False

    integrations = [
        AsyncioIntegration(),
        AioHttpIntegration(),
        LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
    ]
    if component == "web":
        from sentry_sdk.integrations.flask import FlaskIntegration

        integrations.append(FlaskIntegration())

    sentry_sdk.init(
        dsn=target_dsn.strip(),
        environment=SENTRY_ENVIRONMENT,
        release=f"skrepnet@{BOT_VERSION}",
        send_default_pii=False,
        traces_sample_rate=SENTRY_TRACES_RATE,
        max_request_body_size="never",
        max_breadcrumbs=50,
        integrations=integrations,
        before_send=scrub_event,
    )
    sentry_sdk.set_tag("component", component)
    _initialized = True
    logger.info("Sentry включён: %s", component)
    return True


def capture_exception(error: Any) -> bool:
    """Отправляет исключение, если Sentry включён. Возвращает факт отправки."""
    if not _initialized:
        return False
    sentry_sdk.capture_exception(error)
    return True

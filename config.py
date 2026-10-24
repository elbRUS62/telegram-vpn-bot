import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

# Version
BOT_VERSION = os.getenv("BOT_VERSION", "3.7.0")

# Sentry / GlitchTip (необязательно)
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production").strip() or "production"
try:
    SENTRY_TRACES_RATE = float(os.getenv("SENTRY_TRACES_RATE", "0") or 0)
except ValueError:
    SENTRY_TRACES_RATE = 0.0
SENTRY_TRACES_RATE = min(max(SENTRY_TRACES_RATE, 0.0), 1.0)

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_ID", "").split(",") if x.strip()]
SUPERADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("SUPERADMIN_ID", "").split(",")
    if x.strip()
]
# Для старых установок без SUPERADMIN_ID владельцем считается первый ADMIN_ID.
if not SUPERADMIN_IDS and ADMIN_IDS:
    SUPERADMIN_IDS = ADMIN_IDS[:1]
ADMIN_ID = SUPERADMIN_IDS[0] if SUPERADMIN_IDS else (ADMIN_IDS[0] if ADMIN_IDS else 0)
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# Web admin session
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "").strip()
if not WEB_SECRET_KEY:
    WEB_SECRET_KEY = hashlib.sha256(
        f"{BOT_TOKEN or 'skrepnet-web'}:web-admin".encode()
    ).hexdigest()
WEB_ADMIN_SESSION_HOURS = int(os.getenv("WEB_ADMIN_SESSION_HOURS", "12"))
WEB_ADMIN_LINK_TTL_MINUTES = int(os.getenv("WEB_ADMIN_LINK_TTL_MINUTES", "10"))
DIAGNOSTIC_RETENTION_DAYS = int(os.getenv("DIAGNOSTIC_RETENTION_DAYS", "30"))

# Branding
BOT_NAME = os.getenv("BOT_NAME", "SkrepNet")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "SkrepNet_support")

# 3x-ui Panel
XUI_API_TOKEN = os.getenv("XUI_API_TOKEN")
XUI_HOST = os.getenv("XUI_HOST")
XUI_BASE_PATH = os.getenv("XUI_BASE_PATH")

# Inbounds
INBOUND_GB = int(os.getenv("XUI_INBOUND_GB", "5"))

# Subscription
SUB_BASE_URL = os.getenv("SUB_BASE_URL")
SUB_PATH = os.getenv("SUB_PATH")

# Limits
LIMIT_IP = int(os.getenv("LIMIT_IP", "3"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
WEB_SUBSCRIPTION_DAYS = int(os.getenv("WEB_SUBSCRIPTION_DAYS", "3"))

# Donate
DONATE_URL = os.getenv("DONATE_URL")
DONATE_TEXT = os.getenv("DONATE_TEXT")
SERVER_COST = int(os.getenv("SERVER_COST", "3000"))

# Limits
MAX_USERS = int(os.getenv("MAX_USERS", "100"))

# Mini App
MINIAPP_URL = os.getenv("MINIAPP_URL", "")

# Базовый адрес сайта (для ссылок-приглашений). Если не задан — берём из MINIAPP_URL.
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "")
if not WEB_BASE_URL and MINIAPP_URL:
    from urllib.parse import urlsplit
    _parsed = urlsplit(MINIAPP_URL)
    if _parsed.scheme and _parsed.netloc:
        WEB_BASE_URL = f"{_parsed.scheme}://{_parsed.netloc}"

# Web (SSL/port)
SSL_CERT = os.getenv("SSL_CERT", "/root/cert/gb-skrepnet.duckdns.org/fullchain.pem")
SSL_KEY  = os.getenv("SSL_KEY",  "/root/cert/gb-skrepnet.duckdns.org/privkey.pem")
WEB_PORT = int(os.getenv("WEB_PORT", "8443"))

# Database
DB_PATH = os.getenv("DB_PATH", "skrepnet.db")

# Validate
REQUIRED = [
    "BOT_TOKEN",
    "XUI_API_TOKEN",
    "XUI_HOST",
    "XUI_BASE_PATH",
    "SUB_BASE_URL",
    "SUB_PATH"
]
for var in REQUIRED:
    if not os.getenv(var):
        raise ValueError(f"Missing required env variable: {var}")

# 3x-ui panels. Первая панель задаётся старыми XUI_* переменными,
# вторая — необязательными XUI2_*. XUIClient() по умолчанию работает
# с первой панелью, а мониторинг обходит весь список.
def _env_bool(name, default=True):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _normalize_base_path(value):
    value = (value or "").strip()
    return f"/{value.strip('/')}" if value.strip("/") else ""


def _make_panel(panel_id, name, host, base_path, api_token, verify_tls=True):
    host = (host or "").strip().rstrip("/")
    base_path = _normalize_base_path(base_path)
    if not (host and base_path and api_token):
        return None
    return {
        "id": panel_id or "panel",
        "name": name or panel_id or "3x-ui",
        "host": host,
        "base_path": base_path,
        "api_token": api_token,
        "verify_tls": bool(verify_tls),
    }


XUI_PANELS = []

_first_panel = _make_panel(
    os.getenv("XUI_PANEL_ID", "ru"),
    os.getenv("XUI_PANEL_NAME", "RU"),
    XUI_HOST,
    XUI_BASE_PATH,
    XUI_API_TOKEN,
    _env_bool("XUI_VERIFY_TLS", True),
)
if _first_panel:
    XUI_PANELS.append(_first_panel)

_second_values = {
    "XUI2_HOST": os.getenv("XUI2_HOST"),
    "XUI2_BASE_PATH": os.getenv("XUI2_BASE_PATH"),
    "XUI2_API_TOKEN": os.getenv("XUI2_API_TOKEN"),
}
if any(_second_values.values()):
    missing = [key for key, value in _second_values.items() if not value]
    if missing:
        raise ValueError(f"Missing required env variable(s): {', '.join(missing)}")
    _second_panel = _make_panel(
        os.getenv("XUI2_ID", "gb"),
        os.getenv("XUI2_NAME", "GB"),
        _second_values["XUI2_HOST"],
        _second_values["XUI2_BASE_PATH"],
        _second_values["XUI2_API_TOKEN"],
        _env_bool("XUI2_VERIFY_TLS", True),
    )
    if _second_panel:
        XUI_PANELS.append(_second_panel)

if not XUI_PANELS:
    raise ValueError("No 3x-ui panels configured")

_panel_ids = [panel["id"] for panel in XUI_PANELS]
if len(_panel_ids) != len(set(_panel_ids)):
    raise ValueError("Duplicate XUI panel id in XUI_PANELS")
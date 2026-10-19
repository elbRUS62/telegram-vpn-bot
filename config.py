import os
from dotenv import load_dotenv

load_dotenv()

# Version
BOT_VERSION = os.getenv("BOT_VERSION", "3.2.0") 

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_ID", "").split(",") if x.strip()]
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 0  # первый админ, для совместимости
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

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
#!/bin/bash
set -e

# ============================================================
#  SkrepNet Bot — Bot Installer
#  Author: @elbRUS62
#  Repo:   https://github.com/elbRUS62/telegram-vpn-bot
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

header()  { echo ""; echo -e "${BOLD}${BLUE}  $1${NC}"; }
success() { echo -e "${GREEN}  ✅ $1${NC}"; }
error()   { echo -e "${RED}  ❌ $1${NC}"; }
warning() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
info()    { echo -e "${CYAN}  ➜  $1${NC}"; }

echo ""
echo -e "${BOLD}${BLUE}"
echo "        🛡️  SkrepNet Bot — Bot Installer"
echo "        Автор: @elbRUS62"
echo "        GitHub: github.com/elbRUS62/telegram-vpn-bot"
echo -e "${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    error "Запусти скрипт от root (sudo su)"
    exit 1
fi

# Переходим в корень проекта (скрипт лежит в scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [ ! -f "bot.py" ]; then
    error "Файл bot.py не найден. Запусти скрипт из папки бота."
    exit 1
fi

header "Проверка Python"
if ! command -v python3 &> /dev/null; then
    error "Python 3 не найден. Установи: apt install python3"
    exit 1
fi

if ! python3 -m venv --help &> /dev/null; then
    warning "Устанавливаю python3-venv..."
    apt update -qq
    apt install -y python3-venv python3-pip
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
success "Python $PYTHON_VERSION"

if [ -f ".env" ]; then
    warning "Файл .env уже существует."
    read -p "  Перезаписать? (y/N): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        info "Отменено."
        exit 0
    fi
fi

header "Telegram"
read -p "  BOT_TOKEN (от @BotFather): " BOT_TOKEN
read -p "  ADMIN_ID (твой Telegram ID, можно несколько через запятую): " ADMIN_ID
read -p "  BOT_USERNAME (без @, например skrepnet_bot): " BOT_USERNAME
read -p "  BOT_NAME (отображаемое имя бота, например SkrepNet): " BOT_NAME
read -p "  SUPPORT_USERNAME (без @, например SkrepNet_support): " SUPPORT_USERNAME

header "3x-ui Панель"
read -p "  XUI_HOST (например https://ru-skrepnet.duckdns.org:3775): " XUI_HOST
read -p "  XUI_BASE_PATH (например /my_secret_path): " XUI_BASE_PATH
read -p "  XUI_API_TOKEN (из Settings → Security): " XUI_API_TOKEN

header "Проверка 3x-ui"
info "Проверяю доступность API..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 5 --max-time 10 \
    -H "Authorization: Bearer $XUI_API_TOKEN" \
    "${XUI_HOST}${XUI_BASE_PATH}/panel/api/inbounds/list" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    success "Панель доступна, API-токен верный"
elif [ "$HTTP_CODE" = "401" ]; then
    error "Панель ответила 401 Unauthorized — проверь API-токен"
    read -p "  Продолжить всё равно? (y/N): " cont
    [ "$cont" != "y" ] && exit 1
elif [ "$HTTP_CODE" = "000" ]; then
    warning "Не удалось подключиться к панели (проверь XUI_HOST)"
    read -p "  Продолжить всё равно? (y/N): " cont
    [ "$cont" != "y" ] && exit 1
else
    warning "Панель ответила HTTP $HTTP_CODE"
    read -p "  Продолжить всё равно? (y/N): " cont
    [ "$cont" != "y" ] && exit 1
fi

header "Инбаунд 3x-ui"
read -p "  XUI_INBOUND_GB (ID Hysteria2-инбаунда, например 5): " XUI_INBOUND_GB

header "Подписка"
read -p "  SUB_BASE_URL (например https://ru-skrepnet.duckdns.org:9913): " SUB_BASE_URL
read -p "  SUB_PATH (например /subs_77dfgjn5jk78mkldxp77/): " SUB_PATH

header "Лимиты"
read -p "  LIMIT_IP (по умолчанию 3): " LIMIT_IP_INPUT
LIMIT_IP=${LIMIT_IP_INPUT:-3}
read -p "  SUBSCRIPTION_DAYS (по умолчанию 30): " SUBSCRIPTION_DAYS_INPUT
SUBSCRIPTION_DAYS=${SUBSCRIPTION_DAYS_INPUT:-30}
read -p "  MAX_USERS (максимум пользователей, по умолчанию 100): " MAX_USERS_INPUT
MAX_USERS=${MAX_USERS_INPUT:-100}

# Сохраняем значения из существующего .env (если переустановка)
OLD_MINIAPP_URL=""
OLD_WEB_SUBSCRIPTION_DAYS=""
OLD_DONATION_ALERTS_TOKEN=""
OLD_DONATE_URL=""
OLD_DONATE_TEXT=""
OLD_BOT_VERSION=""
if [ -f .env ]; then
    OLD_MINIAPP_URL=$(grep '^MINIAPP_URL=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    OLD_WEB_SUBSCRIPTION_DAYS=$(grep '^WEB_SUBSCRIPTION_DAYS=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    OLD_DONATION_ALERTS_TOKEN=$(grep '^DONATION_ALERTS_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    OLD_DONATE_URL=$(grep '^DONATE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    OLD_DONATE_TEXT=$(grep '^DONATE_TEXT=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    OLD_BOT_VERSION=$(grep '^BOT_VERSION=' .env 2>/dev/null | head -1 | cut -d= -f2-)
fi

header "Mini App (WebApp)"
read -p "  MINIAPP_URL (по умолчанию ${OLD_MINIAPP_URL:-https://gb-skrepnet.duckdns.org:8443/v3}): " MINIAPP_URL_INPUT
MINIAPP_URL=${MINIAPP_URL_INPUT:-${OLD_MINIAPP_URL:-https://gb-skrepnet.duckdns.org:8443/v3}}
read -p "  WEB_SUBSCRIPTION_DAYS (по умолчанию ${OLD_WEB_SUBSCRIPTION_DAYS:-3}): " WEB_DAYS_INPUT
WEB_SUBSCRIPTION_DAYS=${WEB_DAYS_INPUT:-${OLD_WEB_SUBSCRIPTION_DAYS:-3}}
read -p "  DONATION_ALERTS_TOKEN (Enter — оставить текущий): " DONATION_TOKEN_INPUT
DONATION_ALERTS_TOKEN=${DONATION_TOKEN_INPUT:-$OLD_DONATION_ALERTS_TOKEN}

header "Донаты"
read -p "  DONATE_URL (Enter — оставить текущий): " DONATE_URL_INPUT
DONATE_URL=${DONATE_URL_INPUT:-$OLD_DONATE_URL}
read -p "  DONATE_TEXT (Enter — оставить текущий): " DONATE_TEXT_INPUT
DONATE_TEXT=${DONATE_TEXT_INPUT:-$OLD_DONATE_TEXT}
BOT_VERSION=${OLD_BOT_VERSION:-3.4.4}

read -p "  SERVER_COST (стоимость сервера в ₽/мес, например 150): " SERVER_COST



header "Создаю .env"

cat > .env <<EOF
# Telegram
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
BOT_USERNAME=$BOT_USERNAME
BOT_NAME=$BOT_NAME
SUPPORT_USERNAME=$SUPPORT_USERNAME

# 3x-ui Panel
XUI_API_TOKEN=$XUI_API_TOKEN
XUI_HOST=$XUI_HOST
XUI_BASE_PATH=$XUI_BASE_PATH

# Inbound
XUI_INBOUND_GB=$XUI_INBOUND_GB

# Subscription
SUB_BASE_URL=$SUB_BASE_URL
SUB_PATH=$SUB_PATH

# Limits
LIMIT_IP=$LIMIT_IP
SUBSCRIPTION_DAYS=$SUBSCRIPTION_DAYS
MAX_USERS=$MAX_USERS

# Mini App
MINIAPP_URL=$MINIAPP_URL
WEB_SUBSCRIPTION_DAYS=$WEB_SUBSCRIPTION_DAYS

# Donate
DONATE_URL=$DONATE_URL
DONATE_TEXT=$DONATE_TEXT
SERVER_COST=$SERVER_COST
DONATION_ALERTS_TOKEN=$DONATION_ALERTS_TOKEN

# Database
DB_PATH=skrepnet.db

# Version
BOT_VERSION=$BOT_VERSION
EOF

chmod 600 .env
success ".env создан (права 600)"
if ! grep -qE '^DONATION_ALERTS_TOKEN=.+' .env 2>/dev/null; then
    warning "DONATION_ALERTS_TOKEN пуст — впиши в .env, если используешь DonationAlerts"
fi

header "Устанавливаю зависимости"

if [ ! -d "venv" ]; then
    info "Создаю виртуальное окружение (venv)..."
    python3 -m venv venv
    success "venv создан"
else
    info "venv уже существует — использую его"
fi

source venv/bin/activate
info "Обновляю pip (это может занять 10-20 секунд)..."
pip install --upgrade pip 2>&1 | tail -3

info "Устанавливаю зависимости из requirements.txt..."
info "Это займёт 30-60 секунд. Прогресс показывается ниже."
echo ""

if pip install -r requirements.txt; then
    success "Основные зависимости установлены"
else
    error "Ошибка установки зависимостей"
    exit 1
fi

if ! pip show qrcode &> /dev/null; then
    info "Доустанавливаю qrcode[pil]..."
    pip install "qrcode[pil]" 2>&1 | tail -3
fi

success "Все зависимости установлены"

header "Настраиваю бэкапы"
mkdir -p backups
chmod +x backup.sh
success "Папка backups создана"

BACKUP_CRON="0 3 * * * $(pwd)/backup.sh >> $(pwd)/backups/backup.log 2>&1"

if crontab -l 2>/dev/null | grep -q "backup.sh"; then
    warning "Задача бэкапа уже в cron"
else
    (crontab -l 2>/dev/null; echo "$BACKUP_CRON") | crontab -
    success "Бэкапы настроены (ежедневно в 3:00)"
fi

header "Настраиваю systemd (бот)"
cat > /etc/systemd/system/skrepnet-bot.service <<EOF
[Unit]
Description=SkrepNet Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/.env
ExecStart=$(pwd)/venv/bin/python $(pwd)/bot.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable skrepnet-bot
systemctl restart skrepnet-bot
success "Сервис skrepnet-bot настроен и запущен"

echo ""
echo -e "${BOLD}${GREEN}  ✅ Установка бота завершена!${NC}"
echo ""
echo -e "${BOLD}  📋 Команды:${NC}"
echo ""
echo -e "    ${CYAN}systemctl status skrepnet-bot${NC}      — статус"
echo -e "    ${CYAN}journalctl -u skrepnet-bot -f${NC}      — логи"
echo -e "    ${CYAN}systemctl restart skrepnet-bot${NC}     — перезапуск"
echo -e "    ${CYAN}ls -la $(pwd)/backups/${NC}             — бэкапы"
echo -e "    ${CYAN}cd $(pwd)${NC}                          — папка бота"
echo ""
warning "Впиши DONATION_ALERTS_TOKEN в .env и перезапусти бота"
echo ""
echo -e "${BOLD}  🛡️  SkrepNet Bot · @elbRUS62${NC}"
echo ""
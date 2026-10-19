#!/bin/bash
set -e

# ============================================================
#  SkrepNet Bot — Web Installer
#  Author: @elbRUS62
#  Repo:   https://github.com/elbRUS62/skrepnet-bot
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
echo "        🛡️  SkrepNet Bot — Web Installer"
echo "        Автор: @elbRUS62"
echo "        GitHub: github.com/elbRUS62/skrepnet-bot"
echo -e "${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    error "Запусти скрипт от root (sudo su)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [ ! -f "web_app.py" ]; then
    error "Файл web_app.py не найден. Запусти скрипт из папки проекта."
    exit 1
fi

if [ ! -f ".env" ]; then
    error "Файл .env не найден. Сначала запусти scripts/install-bot.sh"
    exit 1
fi

header "Проверка Python и venv"
if [ ! -d "venv" ]; then
    warning "venv не найден — создаю"
    python3 -m venv venv
fi
source venv/bin/activate
success "venv активирован"

header "Параметры веб-сайта"
# Сохраняем текущие домен/порт из .env (если переустановка)
OLD_WEB_DOMAIN=""
OLD_WEB_PORT=""
if [ -f .env ]; then
    _old_url=$(grep '^MINIAPP_URL=' .env 2>/dev/null | head -1 | cut -d= -f2-)
    if [ -n "$_old_url" ]; then
        OLD_WEB_DOMAIN=$(echo "$_old_url" | sed -E 's|^https?://||; s|:[0-9]+.*$||; s|/.*$||')
        OLD_WEB_PORT=$(echo "$_old_url" | sed -nE 's|^https?://[^:]+:([0-9]+).*$|\1|p')
    fi
fi
read -p "  Домен (по умолчанию ${OLD_WEB_DOMAIN:-gb-skrepnet.duckdns.org}): " WEB_DOMAIN_INPUT
WEB_DOMAIN=${WEB_DOMAIN_INPUT:-${OLD_WEB_DOMAIN:-gb-skrepnet.duckdns.org}}
read -p "  Порт (по умолчанию ${OLD_WEB_PORT:-8443}): " WEB_PORT_INPUT
WEB_PORT=${WEB_PORT_INPUT:-${OLD_WEB_PORT:-8443}}

# Добавляем MINIAPP_URL в .env (если нет)
if ! grep -q "^MINIAPP_URL=" .env 2>/dev/null; then
    echo "" >> .env
    echo "# Mini App" >> .env
    echo "MINIAPP_URL=https://${WEB_DOMAIN}:${WEB_PORT}/v3" >> .env
    success "MINIAPP_URL добавлен в .env"
fi

# Добавляем WEB_SUBSCRIPTION_DAYS в .env (если нет)
if ! grep -q "^WEB_SUBSCRIPTION_DAYS=" .env 2>/dev/null; then
    echo "WEB_SUBSCRIPTION_DAYS=3" >> .env
    success "WEB_SUBSCRIPTION_DAYS добавлен в .env"
fi

SSL_CERT_DIR="/root/cert/${WEB_DOMAIN}"
SSL_CERT="${SSL_CERT_DIR}/fullchain.pem"
SSL_KEY="${SSL_CERT_DIR}/privkey.pem"

header "Проверка SSL-сертификатов"
if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
    success "Сертификаты найдены: $SSL_CERT_DIR"
else
    warning "Сертификаты не найдены в $SSL_CERT_DIR"
    read -p "  Получить через certbot? (y/N): " use_certbot
    if [ "$use_certbot" = "y" ] || [ "$use_certbot" = "Y" ]; then
        read -p "  Email для Let's Encrypt: " LE_EMAIL

        if ! command -v certbot &> /dev/null; then
            info "Устанавливаю certbot..."
            apt update -qq
            apt install -y certbot
        fi

        info "Получаю сертификат для $WEB_DOMAIN (standalone, порт 80)..."
        systemctl stop nginx 2>/dev/null || true
        
        if command -v ss > /dev/null 2>&1; then
            if ss -tlnp 2>/dev/null | grep -q ':80 '; then
                warning "Порт 80 занят — certbot --standalone может упасть"
                warning "Освободи порт 80 или используй DNS-валидацию"
                read -p "  Продолжить? (y/N): " cont80
                [ "$cont80" != "y" ] && exit 1
            fi
        fi

        certbot certonly --standalone \
            -d "$WEB_DOMAIN" \
            --email "$LE_EMAIL" \
            --agree-tos --non-interactive

        mkdir -p "$SSL_CERT_DIR"
        cp "/etc/letsencrypt/live/${WEB_DOMAIN}/fullchain.pem" "$SSL_CERT"
        cp "/etc/letsencrypt/live/${WEB_DOMAIN}/privkey.pem" "$SSL_KEY"
        chmod 600 "$SSL_KEY"

        success "Сертификаты получены и скопированы в $SSL_CERT_DIR"
    else
        warning "Сайт будет запущен БЕЗ HTTPS (порт ${WEB_PORT} без TLS)"
    fi
fi

header "Прописываю SSL/port в .env"
# SSL_CERT / SSL_KEY / WEB_PORT — идемпотентно (как MINIAPP_URL выше)
for _var in SSL_CERT SSL_KEY WEB_PORT; do
    if ! grep -q "^${_var}=" .env 2>/dev/null; then
        case $_var in
            SSL_CERT) echo "SSL_CERT=${SSL_CERT}" >> .env ;;
            SSL_KEY)  echo "SSL_KEY=${SSL_KEY}"   >> .env ;;
            WEB_PORT) echo "WEB_PORT=${WEB_PORT}" >> .env ;;
        esac
    fi
done
success "SSL/port прописаны в .env (web_app.py не трогаем)"

header "Устанавливаю зависимости (если нужно)"
pip install -r requirements.txt -q
success "Зависимости на месте"

header "Настраиваю systemd (сайт)"
EXISTING_UNIT="/etc/systemd/system/skrepnet-web.service"
if [ -f "$EXISTING_UNIT" ]; then
    EXISTING_WD=$(grep -E '^WorkingDirectory=' "$EXISTING_UNIT" | head -1 | cut -d= -f2-)
    if [ -n "$EXISTING_WD" ] && [ "$EXISTING_WD" != "$(pwd)" ]; then
        warning "Существующий unit указывает на: $EXISTING_WD"
        warning "Текущая директория:              $(pwd)"
        read -p "  Перезаписать unit? (y/N): " overwrite_unit
        if [ "$overwrite_unit" != "y" ] && [ "$overwrite_unit" != "Y" ]; then
            error "Отменено (unit не перезаписан)"
            exit 1
        fi
    fi
fi
cat > /etc/systemd/system/skrepnet-web.service <<EOF
[Unit]
Description=SkrepNet Web (Flask)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/.env
Environment="PYTHONUNBUFFERED=1"
ExecStart=$(pwd)/venv/bin/python $(pwd)/web_app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable skrepnet-web.service
systemctl restart skrepnet-web
success "Сервис skrepnet-web настроен и запущен"

echo ""
echo -e "${BOLD}${GREEN}  ✅ Установка веб-сайта завершена!${NC}"
echo ""

if [ -f "$SSL_CERT" ]; then
    echo -e "${BOLD}  🌐 Сайт:${NC} ${CYAN}https://${WEB_DOMAIN}:${WEB_PORT}/invite/<token>${NC}"
else
    echo -e "${BOLD}  🌐 Сайт:${NC} ${CYAN}http://${WEB_DOMAIN}:${WEB_PORT}/invite/<token>${NC}"
fi
echo ""
echo -e "${BOLD}  📋 Команды:${NC}"
echo ""
echo -e "    ${CYAN}systemctl status skrepnet-web${NC}      — статус"
echo -e "    ${CYAN}journalctl -u skrepnet-web -f${NC}      — логи"
echo -e "    ${CYAN}systemctl restart skrepnet-web${NC}     — перезапуск"
echo ""
echo -e "${BOLD}  🛡️  SkrepNet Bot · @elbRUS62${NC}"
echo ""
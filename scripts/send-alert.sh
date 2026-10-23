#!/bin/bash
set -euo pipefail

ENV_FILE="${ALERT_ENV_FILE:-/root/.config/skrepnet-alerts.env}"
MESSAGE="${1:-SkrepNet alert}"

if [ ! -f "$ENV_FILE" ]; then
    echo "alert config not found: $ENV_FILE" >&2
    exit 0
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

if [ -z "${ALERT_BOT_TOKEN:-}" ] || [ -z "${ALERT_CHAT_ID:-}" ]; then
    echo "alert bot is not configured" >&2
    exit 0
fi

curl -fsS --max-time 15 \
    -X POST "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${ALERT_CHAT_ID}" \
    --data-urlencode "text=${MESSAGE}" \
    --data-urlencode "disable_web_page_preview=true" \
    >/dev/null

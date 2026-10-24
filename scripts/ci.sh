#!/bin/bash
# Единая проверка проекта: компиляция, тесты, синтаксис JS.
# Используется локально, в pre-push хуке и в GitHub Actions.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON="${PYTHON:-./venv/bin/python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON=python3
fi

TMP_DB="$(mktemp "${TMPDIR:-/tmp}/skrepnet-ci-XXXXXX.db")"
cleanup() {
    rm -f "$TMP_DB" "$TMP_DB-wal" "$TMP_DB-shm"
}
trap cleanup EXIT

export PYTHONPATH="$PWD"
export DB_PATH="$TMP_DB"
export BOT_TOKEN="${BOT_TOKEN:-123456:CI}"
export ADMIN_ID="${ADMIN_ID:-1}"
export SUPERADMIN_ID="${SUPERADMIN_ID:-1}"
export BOT_USERNAME="${BOT_USERNAME:-ci_bot}"
export XUI_HOST="${XUI_HOST:-http://127.0.0.1:9}"
export XUI_BASE_PATH="${XUI_BASE_PATH:-/panel}"
export XUI_API_TOKEN="${XUI_API_TOKEN:-ci-token}"
export XUI_VERIFY_TLS="${XUI_VERIFY_TLS:-false}"
export SUB_BASE_URL="${SUB_BASE_URL:-http://127.0.0.1:9}"
export SUB_PATH="${SUB_PATH:-sub}"

echo "== Python: компиляция =="
"$PYTHON" -m compileall -q -x '(/|^)venv/' .

echo "== Python: тесты =="
"$PYTHON" -m unittest discover -s tests -q

echo "== JavaScript: синтаксис =="
if command -v node >/dev/null 2>&1; then
    for file in web/static/*.js; do
        node --check "$file"
        echo "ok: $file"
    done
else
    echo "node не найден — проверка JS пропущена"
fi

echo "CI: всё в порядке"

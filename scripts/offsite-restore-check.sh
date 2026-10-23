#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${OFFSITE_ENV_FILE:-/root/.config/skrepnet-offsite/offsite.env}"
TMP_DIR="$(mktemp -d)"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

alert() {
    "$SCRIPT_DIR/send-alert.sh" "$*" || true
}

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail() {
    log "ERROR: $*"
    alert "SkrepNet restore check: $*"
    exit 1
}

[ -f "$ENV_FILE" ] || fail "config not found: $ENV_FILE"

# shellcheck disable=SC1090
source "$ENV_FILE"

for name in RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY RESTIC_PASSWORD_FILE; do
    value="${!name:-}"
    [ -n "$value" ] || fail "not configured: $name"
done

[ -f "$RESTIC_PASSWORD_FILE" ] || fail "restic password file not found: $RESTIC_PASSWORD_FILE"
command -v restic >/dev/null 2>&1 || fail "restic is not installed"

export RESTIC_REPOSITORY
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export RESTIC_PASSWORD_FILE
export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/root/.cache/restic}"
[ -n "${AWS_DEFAULT_REGION:-}" ] && export AWS_DEFAULT_REGION

log "restoring latest snapshot"
if ! restic restore latest --target "$TMP_DIR"; then
    fail "restic restore failed"
fi

restored_db="$(find "$TMP_DIR" -type f -name 'skrepnet-*.db' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[ -n "$restored_db" ] || fail "no database found in restored snapshot"

log "verifying restored database: $(basename "$restored_db")"
if ! "$SCRIPT_DIR/verify_backup.py" "$restored_db"; then
    fail "restored database verification failed"
fi

if [ -n "${UPTIMEROBOT_RESTORE_URL:-}" ]; then
    if ! curl -fsS --max-time 15 "$UPTIMEROBOT_RESTORE_URL" >/dev/null; then
        fail "UptimeRobot restore heartbeat failed"
    fi
fi

log "restore check complete"

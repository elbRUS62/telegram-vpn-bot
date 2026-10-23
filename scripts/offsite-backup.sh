#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../backups"
ENV_FILE="${OFFSITE_ENV_FILE:-/root/.config/skrepnet-offsite/offsite.env}"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

alert() {
    "$SCRIPT_DIR/send-alert.sh" "$*" || true
}

fail() {
    log "ERROR: $*"
    alert "SkrepNet offsite backup: $*"
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
mkdir -p "$RESTIC_CACHE_DIR"

latest="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'skrepnet-*.db' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[ -n "$latest" ] || fail "no local backups found in $BACKUP_DIR"

log "latest local backup: $(basename "$latest")"

verify_output="$(mktemp)"
trap 'rm -f "$verify_output"' EXIT
if ! "$SCRIPT_DIR/verify_backup.py" "$latest" >"$verify_output" 2>&1; then
    cat "$verify_output" >&2
    fail "local backup verification failed"
fi

files=("$latest")
[ -f "$latest.sha256" ] && files+=("$latest.sha256")
[ -f "$latest.json" ] && files+=("$latest.json")

if ! restic snapshots >/dev/null 2>&1; then
    fail "restic repository is not initialized or unavailable"
fi

log "uploading to offsite storage"
if ! restic backup "${files[@]}" --tag skrepnet-db --host "$(hostname)"; then
    fail "restic backup failed"
fi

log "applying retention"
if ! restic forget --keep-daily 30 --keep-weekly 8 --keep-monthly 6 --prune; then
    fail "restic forget/prune failed"
fi

if [ -n "${UPTIMEROBOT_BACKUP_URL:-}" ]; then
    if ! curl -fsS --max-time 15 "$UPTIMEROBOT_BACKUP_URL" >/dev/null; then
        fail "UptimeRobot heartbeat failed"
    fi
else
    log "WARNING: UPTIMEROBOT_BACKUP_URL is empty"
fi

log "offsite backup complete"

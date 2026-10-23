#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${OFFSITE_ENV_FILE:-/root/.config/skrepnet-offsite/offsite.env}"

fail() {
    echo "ERROR: $*" >&2
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

if restic snapshots >/dev/null 2>&1; then
    echo "restic repository is already initialized"
    exit 0
fi

restic init
"$SCRIPT_DIR/send-alert.sh" "SkrepNet offsite backup initialized" || true
echo "restic repository initialized"

#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../backups"

if [[ $# -gt 0 ]]; then
    TARGET="$1"
else
    TARGET="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'skrepnet-*.db' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
fi

if [[ -z "${TARGET:-}" || ! -f "$TARGET" ]]; then
    echo "Backup not found" >&2
    exit 1
fi

exec "$SCRIPT_DIR/../venv/bin/python3" "$SCRIPT_DIR/verify_backup.py" "$TARGET"

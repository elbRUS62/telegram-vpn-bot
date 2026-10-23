#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/backups"
DB_FILE="$SCRIPT_DIR/skrepnet.db"
PYTHON="$SCRIPT_DIR/venv/bin/python3"
DATE="$(date +%Y-%m-%d_%H-%M)"
TARGET="$BACKUP_DIR/skrepnet-$DATE.db"

mkdir -p "$BACKUP_DIR"

"$PYTHON" - "$DB_FILE" "$TARGET" <<'PY'
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime

source_path, target_path = sys.argv[1], sys.argv[2]
if not os.path.exists(source_path):
    raise SystemExit(f"database not found: {source_path}")

source = sqlite3.connect(source_path)
target = sqlite3.connect(target_path)
try:
    source.backup(target)
    target.execute("PRAGMA journal_mode=DELETE")
    integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"integrity_check failed: {integrity}")

    counts = {}
    for table in (
        "users",
        "invite_links",
        "invites",
        "donations",
        "waitlist",
        "support_tickets",
        "support_messages",
        "monitor_state",
        "monitor_metrics",
        "admin_audit",
    ):
        try:
            counts[table] = target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[table] = None
finally:
    target.close()
    source.close()

with open(target_path, "rb") as backup_file:
    digest = hashlib.sha256(backup_file.read()).hexdigest()

with open(target_path + ".sha256", "w", encoding="utf-8") as checksum_file:
    checksum_file.write(f"{digest}  {os.path.basename(target_path)}\n")

metadata = {
    "file": os.path.basename(target_path),
    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "size_bytes": os.path.getsize(target_path),
    "sha256": digest,
    "integrity_check": integrity,
    "counts": counts,
}
with open(target_path + ".json", "w", encoding="utf-8") as meta_file:
    json.dump(metadata, meta_file, ensure_ascii=False, indent=2)

print(json.dumps(metadata, ensure_ascii=False))
PY

find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'skrepnet-*.db' -o -name 'skrepnet-*.db.sha256' -o -name 'skrepnet-*.db.json' \) \
    -mtime +30 -delete

echo "$(date '+%Y-%m-%d %H:%M:%S') Backup created: $(basename "$TARGET")"

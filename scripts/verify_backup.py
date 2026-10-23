#!/usr/bin/env python3
"""Проверка резервной копии SQLite: восстановление, integrity_check и счётчики."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

REQUIRED_TABLES = {
    "users",
    "invite_links",
    "invites",
    "donations",
    "waitlist",
    "support_tickets",
    "support_messages",
    "monitor_state",
    "monitor_metrics",
}

COUNT_TABLES = (
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
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_expected_checksum(path: Path) -> str | None:
    checksum_file = Path(str(path) + ".sha256")
    if not checksum_file.is_file():
        return None
    line = checksum_file.read_text(encoding="utf-8").strip()
    return line.split()[0] if line else None


def verify(backup_path: Path) -> dict:
    if not backup_path.is_file():
        raise FileNotFoundError(f"backup not found: {backup_path}")

    result = {
        "backup": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "sha256": sha256(backup_path),
        "checksum_ok": True,
        "integrity_check": None,
        "missing_tables": [],
        "counts": {},
        "ok": False,
    }

    expected = read_expected_checksum(backup_path)
    if expected:
        result["checksum_ok"] = expected == result["sha256"]

    with tempfile.TemporaryDirectory(prefix="skrepnet-restore-") as temp_dir:
        restored = Path(temp_dir) / "restored.db"
        shutil.copy2(backup_path, restored)

        connection = sqlite3.connect(restored)
        try:
            result["integrity_check"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            result["missing_tables"] = sorted(REQUIRED_TABLES - tables)
            for table in COUNT_TABLES:
                if table not in tables:
                    result["counts"][table] = None
                    continue
                result["counts"][table] = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
        finally:
            connection.close()

    result["ok"] = (
        result["checksum_ok"]
        and result["integrity_check"] == "ok"
        and not result["missing_tables"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверить восстановление SQLite-бэкапа")
    parser.add_argument("backup", type=Path, help="путь к файлу .db")
    args = parser.parse_args()

    try:
        result = verify(args.backup)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

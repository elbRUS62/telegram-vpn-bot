"""Одноразовые ссылки и сессионная авторизация веб-админки."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from config import DB_PATH, WEB_ADMIN_LINK_TTL_MINUTES


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def create_login_token(admin_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=WEB_ADMIN_LINK_TTL_MINUTES)
    ).strftime("%Y-%m-%d %H:%M:%S")

    connection = _connect()
    try:
        connection.execute(
            "DELETE FROM admin_login_tokens "
            "WHERE used_at IS NOT NULL OR expires_at < ?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        connection.execute(
            "INSERT INTO admin_login_tokens(token_hash, admin_id, expires_at) "
            "VALUES (?, ?, ?)",
            (_hash(token), int(admin_id), expires_at),
        )
        connection.commit()
    finally:
        connection.close()

    return token


def consume_login_token(token: str):
    if not token or len(token) < 20:
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, admin_id, expires_at, used_at "
            "FROM admin_login_tokens WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
        if not row:
            connection.rollback()
            return None
        if row["used_at"] or row["expires_at"] < now:
            connection.rollback()
            return None

        connection.execute(
            "UPDATE admin_login_tokens SET used_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        connection.commit()
        return int(row["admin_id"])
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def audit(admin_id: int, action: str, target_id=None, meta: str = ""):
    connection = _connect()
    try:
        connection.execute(
            "INSERT INTO admin_audit(admin_id, action, target_id, meta) "
            "VALUES (?, ?, ?, ?)",
            (int(admin_id), action, target_id, meta),
        )
        connection.commit()
    finally:
        connection.close()

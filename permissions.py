"""Роли администраторов и суперадминистраторов.

Источник истины — таблица admins. Переменные SUPERADMIN_ID/ADMIN_ID
используются только для первичного заполнения и аварийного доступа.
"""

import logging
import sqlite3
from contextlib import contextmanager

from config import ADMIN_IDS, DB_PATH, SUPERADMIN_IDS

logger = logging.getLogger(__name__)

ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
VALID_ROLES = {ROLE_ADMIN, ROLE_SUPERADMIN}

_SCHEMA_READY = False


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _db():
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def ensure_admin_schema():
    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    with _db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                role TEXT NOT NULL DEFAULT 'admin',
                is_active INTEGER NOT NULL DEFAULT 1,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(admins)").fetchall()
        }
        additions = {
            "first_name": "TEXT",
            "role": "TEXT NOT NULL DEFAULT 'admin'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "updated_at": "TIMESTAMP",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE admins ADD COLUMN {name} {definition}"
                )
        connection.commit()

    _SCHEMA_READY = True


def _next_role(telegram_id):
    return (
        ROLE_SUPERADMIN
        if int(telegram_id) in SUPERADMIN_IDS
        else ROLE_ADMIN
    )


def _insert_admin(connection, telegram_id, username="", first_name="",
                  role=ROLE_ADMIN, added_by=None):
    connection.execute(
        """
        INSERT INTO admins
            (telegram_id, username, first_name, role, is_active, added_by,
             added_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = COALESCE(NULLIF(excluded.username, ''), admins.username),
            first_name = COALESCE(NULLIF(excluded.first_name, ''), admins.first_name),
            role = excluded.role,
            is_active = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(telegram_id),
            (username or "").strip(),
            (first_name or "").strip(),
            role if role in VALID_ROLES else ROLE_ADMIN,
            added_by,
        ),
    )


def seed_admins():
    """Создаёт таблицу и переносит ADMIN_ID в неё при первом запуске."""
    ensure_admin_schema()

    with _db() as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM admins"
        ).fetchone()[0]

        # При первом запуске переносим всех старых админов из ADMIN_ID.
        if total == 0:
            for telegram_id in ADMIN_IDS:
                _insert_admin(
                    connection,
                    telegram_id,
                    role=_next_role(telegram_id),
                    added_by=None,
                )

        # Суперадмин из окружения должен существовать всегда.
        for telegram_id in SUPERADMIN_IDS:
            _insert_admin(
                connection,
                telegram_id,
                role=ROLE_SUPERADMIN,
                added_by=None,
            )
        connection.commit()

    logger.info(
        "admins seeded: %s, superadmins: %s",
        len(ADMIN_IDS),
        len(SUPERADMIN_IDS),
    )


def _get_row(telegram_id):
    ensure_admin_schema()
    with _db() as connection:
        return connection.execute(
            "SELECT * FROM admins WHERE telegram_id = ?",
            (int(telegram_id),),
        ).fetchone()


def _has_any_admins():
    ensure_admin_schema()
    with _db() as connection:
        return bool(
            connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone()
        )


def is_superadmin(telegram_id):
    try:
        telegram_id = int(telegram_id or 0)
    except (TypeError, ValueError):
        return False
    if telegram_id in SUPERADMIN_IDS:
        return True
    row = _get_row(telegram_id)
    return bool(
        row
        and row["is_active"]
        and row["role"] == ROLE_SUPERADMIN
    )


def is_admin_user(telegram_id):
    try:
        telegram_id = int(telegram_id or 0)
    except (TypeError, ValueError):
        return False
    if telegram_id in SUPERADMIN_IDS:
        return True

    row = _get_row(telegram_id)
    if row is not None:
        return bool(row["is_active"])

    # Аварийный мост для первого запуска до seed_admins().
    if not _has_any_admins():
        return telegram_id in ADMIN_IDS
    return False


def get_admin_role(telegram_id):
    try:
        telegram_id = int(telegram_id or 0)
    except (TypeError, ValueError):
        return None
    if telegram_id in SUPERADMIN_IDS:
        return ROLE_SUPERADMIN
    row = _get_row(telegram_id)
    if not row or not row["is_active"]:
        return None
    return row["role"] or ROLE_ADMIN


def get_admin_ids():
    """ID всех активных админов для уведомлений."""
    result = []
    for telegram_id in SUPERADMIN_IDS:
        if telegram_id not in result:
            result.append(telegram_id)

    try:
        ensure_admin_schema()
        with _db() as connection:
            rows = connection.execute(
                "SELECT telegram_id FROM admins WHERE is_active = 1 "
                "ORDER BY telegram_id"
            ).fetchall()
        for row in rows:
            telegram_id = int(row[0])
            if telegram_id not in result:
                result.append(telegram_id)
    except Exception:
        logger.exception("Не удалось прочитать список админов")
        for telegram_id in ADMIN_IDS:
            if telegram_id not in result:
                result.append(telegram_id)

    return result


def list_admins():
    ensure_admin_schema()
    with _db() as connection:
        rows = connection.execute("""
            SELECT a.telegram_id, a.role, a.is_active, a.added_by, a.added_at,
                   COALESCE(NULLIF(u.username, ''), a.username, '') AS username,
                   COALESCE(NULLIF(u.first_name, ''), a.first_name, '') AS first_name
            FROM admins a
            LEFT JOIN users u ON u.telegram_id = a.telegram_id
            ORDER BY CASE a.role WHEN 'superadmin' THEN 0 ELSE 1 END,
                     a.added_at, a.telegram_id
        """).fetchall()
    result = []
    for row in rows:
        admin = dict(row)
        admin["protected"] = int(admin["telegram_id"]) in SUPERADMIN_IDS
        result.append(admin)
    return result


def save_admin(telegram_id, username="", first_name="", role=ROLE_ADMIN,
               added_by=None):
    ensure_admin_schema()
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        raise ValueError("Некорректный Telegram ID")
    if telegram_id <= 0:
        raise ValueError("Некорректный Telegram ID")
    if role not in VALID_ROLES:
        raise ValueError("Неизвестная роль")

    if telegram_id in SUPERADMIN_IDS:
        role = ROLE_SUPERADMIN

    with _db() as connection:
        _insert_admin(
            connection,
            telegram_id,
            username=username,
            first_name=first_name,
            role=role,
            added_by=added_by,
        )
        connection.commit()
    return get_admin_role(telegram_id)


def set_admin_role(telegram_id, role, actor_id=None):
    ensure_admin_schema()
    if role not in VALID_ROLES:
        raise ValueError("Неизвестная роль")
    telegram_id = int(telegram_id)

    if telegram_id in SUPERADMIN_IDS and role != ROLE_SUPERADMIN:
        raise ValueError("Нельзя понизить суперадмина из окружения")

    with _db() as connection:
        row = connection.execute(
            "SELECT role, is_active FROM admins WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            raise ValueError("Админ не найден")

        if row["role"] == ROLE_SUPERADMIN and role != ROLE_SUPERADMIN:
            count = connection.execute(
                "SELECT COUNT(*) FROM admins "
                "WHERE role = 'superadmin' AND is_active = 1"
            ).fetchone()[0]
            if count <= 1:
                raise ValueError("Нельзя оставить сервис без суперадмина")

        connection.execute(
            "UPDATE admins SET role = ?, is_active = 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            (role, telegram_id),
        )
        connection.commit()

    return role


def deactivate_admin(telegram_id, actor_id=None):
    ensure_admin_schema()
    telegram_id = int(telegram_id)

    if telegram_id in SUPERADMIN_IDS:
        raise ValueError("Нельзя удалить суперадмина из окружения")

    with _db() as connection:
        row = connection.execute(
            "SELECT role, is_active FROM admins WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            raise ValueError("Админ не найден")

        if row["role"] == ROLE_SUPERADMIN:
            count = connection.execute(
                "SELECT COUNT(*) FROM admins "
                "WHERE role = 'superadmin' AND is_active = 1"
            ).fetchone()[0]
            if count <= 1:
                raise ValueError("Нельзя удалить последнего суперадмина")

        connection.execute(
            "UPDATE admins SET is_active = 0, "
            "updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.commit()
    return True


def get_admin_summary(telegram_id):
    role = get_admin_role(telegram_id)
    return {
        "role": role,
        "is_admin": role is not None,
        "is_superadmin": role == ROLE_SUPERADMIN,
    }

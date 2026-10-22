import logging
import aiosqlite
import secrets
from datetime import datetime, timedelta

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                xui_email TEXT UNIQUE,
                sub_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                notified_3d INTEGER DEFAULT 0,
                notified_0d INTEGER DEFAULT 0,
                invited_by INTEGER,
                invites_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                token TEXT PRIMARY KEY,
                created_by INTEGER NOT NULL,
                friend_user_id INTEGER,
                friend_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                xui_email TEXT,
                sub_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER NOT NULL,
                invited_user_id INTEGER,
                invited_username TEXT,
                invited_first_name TEXT,
                type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'RUB',
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Миграция: добавляем поле renew_count, если его нет
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]

        if "renew_count" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN renew_count INTEGER DEFAULT 0")
            logger.info("🔧 Добавлено поле renew_count в таблицу users")
        # Миграция: добавляем поля в invite_links для веб-привязки
        async with db.execute("PRAGMA table_info(invite_links)") as cur:
            il_columns = [row[1] for row in await cur.fetchall()]

        if "counted" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN counted INTEGER DEFAULT 0")
            logger.info("🔧 Добавлено поле counted в invite_links")

        if "bound_to_tg_id" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN bound_to_tg_id INTEGER DEFAULT NULL")
            logger.info("🔧 Добавлено поле bound_to_tg_id в invite_links")

        if "bound_at" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN bound_at TIMESTAMP DEFAULT NULL")
            logger.info("🔧 Добавлено поле bound_at в invite_links")
            
        await db.commit()


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================

async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            return await cursor.fetchone()


async def get_user_by_username(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cursor:
            return await cursor.fetchone()


async def create_user_request(telegram_id: int, username: str, first_name: str,
                               xui_email: str, invited_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users
            (telegram_id, username, first_name, xui_email, status, invited_by)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (telegram_id, username, first_name, xui_email, invited_by))
        await db.commit()


async def approve_user(telegram_id: int, sub_id: str, days: int = SUBSCRIPTION_DAYS):
    expires = datetime.now() + timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET status = 'active', sub_id = ?, expires_at = ?,
            notified_3d = 0, notified_0d = 0
            WHERE telegram_id = ?
        """, (sub_id, expires, telegram_id))
        await db.commit()


async def renew_user(telegram_id: int, new_expires=None, days: int = SUBSCRIPTION_DAYS):
    if new_expires is None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT expires_at FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row and row["expires_at"]:
                current = datetime.fromisoformat(row["expires_at"])
                new_expires = max(current, datetime.now()) + timedelta(days=days)
            else:
                new_expires = datetime.now() + timedelta(days=days)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET expires_at = ?, notified_3d = 0, notified_0d = 0
            WHERE telegram_id = ?
        """, (new_expires, telegram_id))
        await db.commit()
        return new_expires


async def get_expiring_users(days: int):
    target_date = (datetime.now() + timedelta(days=days)).date()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND DATE(expires_at) = ?
            AND notified_3d = 0
        """, (target_date,)) as cursor:
            return await cursor.fetchall()


async def get_expired_today():
    today = datetime.now().date()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND DATE(expires_at) = ?
            AND notified_0d = 0
        """, (today,)) as cursor:
            return await cursor.fetchall()


async def mark_notified(telegram_id: int, field: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = 1 WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def increment_invites(inviter_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET invites_count = invites_count + 1
            WHERE telegram_id = ?
        """, (inviter_id,))
        await db.commit()


async def delete_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def get_inactive_users(days: int = 30) -> list:
    """Пользователи, у которых подписка истекла более N дней назад."""
    cutoff = datetime.now() - timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'active'
            AND expires_at < ?
        """, (cutoff,)) as cur:
            return await cur.fetchall()


# ============================================================
# ОДНОРАЗОВЫЕ ССЫЛКИ-ПРИГЛАШЕНИЯ (для друзей без Telegram)
# ============================================================

async def create_invite_link(telegram_id: int, friend_user_id: int = None,
                              friend_username: str = None) -> str:
    """Создаёт или переиспользует ссылку-приглашение.

    Приоритет: если на того же друга уже есть ссылка — она переиспользуется
    (is_used сбрасывается в 0, created_at обновляется), чтобы не копить мусор
    в БД. Если ссылки нет — создаётся новая.
    """
    # --- Попытка переиспользовать существующую ссылку ---
    async with aiosqlite.connect(DB_PATH) as db:
        existing_token = None
        if friend_user_id is not None:
            async with db.execute("""
                SELECT token FROM invite_links
                WHERE created_by = ? AND friend_user_id = ?
                ORDER BY created_at DESC LIMIT 1
            """, (telegram_id, friend_user_id)) as cur:
                row = await cur.fetchone()
                if row:
                    existing_token = row[0]
        elif friend_username:
            async with db.execute("""
                SELECT token FROM invite_links
                WHERE created_by = ? AND friend_username = ?
                ORDER BY created_at DESC LIMIT 1
            """, (telegram_id, friend_username)) as cur:
                row = await cur.fetchone()
                if row:
                    existing_token = row[0]

        if existing_token:
            await db.execute("""
                UPDATE invite_links
                SET is_used = 0,
                    used_at = NULL,
                    created_at = CURRENT_TIMESTAMP,
                    counted = 0,
                    xui_email = NULL,
                    sub_id = NULL
                WHERE token = ?
            """, (existing_token,))
            await db.commit()
            logger.info(
                "♻️ Переиспользована ссылка %s (created_by=%s, friend_id=%s, friend_username=%s)",
                existing_token, telegram_id, friend_user_id, friend_username,
            )
            return existing_token
    # --- Конец переиспользования, создаём новую ---

    token = secrets.token_urlsafe(24)

    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем старые неактивные ссылки того же A на того же друга
        # Условие: (A, friend) совпадают, ссылка не использована
        if friend_user_id is not None:
            # Друг известен по TG ID — удаляем по нему
            await db.execute("""
                DELETE FROM invite_links
                WHERE created_by = ?
                  AND is_used = 0
                  AND friend_user_id = ?
            """, (telegram_id, friend_user_id))

        elif friend_username:
            # Друг известен по username — удаляем по нему
            await db.execute("""
                DELETE FROM invite_links
                WHERE created_by = ?
                  AND is_used = 0
                  AND friend_username = ?
            """, (telegram_id, friend_username))

        # Создаём новую ссылку
        await db.execute("""
            INSERT INTO invite_links
            (token, created_by, friend_user_id, friend_username)
            VALUES (?, ?, ?, ?)
        """, (token, telegram_id, friend_user_id, friend_username))
        await db.commit()

    return token


async def use_invite_link(token: str, xui_email: str, sub_id: str) -> bool:
    """Помечает ссылку использованной и сохраняет данные клиента."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE invite_links
            SET is_used = 1, used_at = ?, xui_email = ?, sub_id = ?
            WHERE token = ? AND is_used = 0
        """, (datetime.now(), xui_email, sub_id, token))
        await db.commit()
        return cursor.rowcount > 0



# ============================================================
# УЧЁТ ПРИГЛАШЕНИЙ (для админ-статистики)
# ============================================================

async def add_invite(inviter_id: int, invited_user_id: int = None,
                      invited_username: str = None, invited_first_name: str = None,
                      invite_type: str = "ref"):
    """Записывает приглашение.
    invite_type: 'ref' (реферальная) или 'no_tg' (без Telegram).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO invites
            (inviter_id, invited_user_id, invited_username, invited_first_name, type)
            VALUES (?, ?, ?, ?, ?)
        """, (inviter_id, invited_user_id, invited_username, invited_first_name, invite_type))
        await db.commit()


async def get_global_invites_stats() -> dict:
    """Общая статистика по всем приглашениям."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT COUNT(*) as c FROM invites WHERE type = 'ref'"
        ) as cur:
            ref_count = (await cur.fetchone())["c"]

        async with db.execute(
            "SELECT COUNT(*) as c FROM invites WHERE type = 'no_tg'"
        ) as cur:
            no_tg_count = (await cur.fetchone())["c"]

        return {
            "ref": ref_count,
            "no_tg": no_tg_count,
            "total": ref_count + no_tg_count
        }


async def get_top_inviters(limit: int = 5) -> list:
    """Топ пользователей по количеству приглашений."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                inviter_id,
                COUNT(CASE WHEN type = 'ref' THEN 1 END) as ref_count,
                COUNT(CASE WHEN type = 'no_tg' THEN 1 END) as no_tg_count,
                COUNT(*) as total
            FROM invites
            GROUP BY inviter_id
            ORDER BY total DESC
            LIMIT ?
        """, (limit,)) as cur:
            return await cur.fetchall()


async def get_pending_requests() -> list:
    """Все заявки со статусом pending или rejected."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users
            WHERE status IN ('pending', 'rejected')
            ORDER BY created_at DESC
        """) as cur:
            return await cur.fetchall()


async def reject_user(telegram_id: int):
    """Помечает заявку как отклонённую."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET status = 'rejected' WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()


# ============================================================
# ПАГИНАЦИЯ ПОЛЬЗОВАТЕЛЕЙ (для админ-списков)
# ============================================================

async def get_users_paginated(statuses: list, offset: int = 0, limit: int = 10) -> list:
    """Получить пользователей с определёнными статусами, с пагинацией.

    Args:
        statuses: список статусов, например ['active', 'pending']
        offset: сколько пропустить
        limit: сколько вернуть
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(statuses))
        async with db.execute(f"""
            SELECT * FROM users
            WHERE status IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (*statuses, limit, offset)) as cur:
            return await cur.fetchall()


async def count_users_by_statuses(statuses: list) -> int:
    """Сколько пользователей с указанными статусами.

    Args:
        statuses: список статусов, например ['active', 'pending']
    """
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" * len(statuses))
        async with db.execute(f"""
            SELECT COUNT(*) FROM users WHERE status IN ({placeholders})
        """, statuses) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# ============================================================
# ДОНАТЫ
# ============================================================

async def add_donation(username: str, amount: float, currency: str = "RUB", message: str = None):
    """Записать донат в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO donations (username, amount, currency, message)
            VALUES (?, ?, ?, ?)
        """, (username, amount, currency, message))
        await db.commit()


async def get_donations_total(currency: str = "RUB") -> float:
    """Сумма всех донатов за текущий месяц в указанной валюте."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM donations
            WHERE currency = ?
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """, (currency,)) as cur:
            row = await cur.fetchone()
            return float(row[0]) if row else 0.0


# ============================================================
# ЛИСТ ОЖИДАНИЯ
# ============================================================

async def add_to_waitlist(telegram_id: int, username: str, first_name: str) -> bool:
    """Добавить в лист ожидания. Возвращает True, если добавлен, False, если уже был."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO waitlist (telegram_id, username, first_name)
                VALUES (?, ?, ?)
            """, (telegram_id, username, first_name))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_waitlist_position(telegram_id: int) -> int | None:
    """Позиция в очереди (1-based) или None, если не в очереди."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM waitlist
            WHERE id <= (SELECT id FROM waitlist WHERE telegram_id = ?)
        """, (telegram_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] > 0 else None


async def get_waitlist_count() -> int:
    """Сколько человек в листе ожидания."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM waitlist") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def pop_from_waitlist() -> dict | None:
    """Взять первого из очереди и удалить его из waitlist.
    Возвращает данные пользователя или None, если очередь пуста."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM waitlist ORDER BY id ASC LIMIT 1
        """) as cur:
            row = await cur.fetchone()

        if not row:
            return None

        await db.execute("DELETE FROM waitlist WHERE id = ?", (row["id"],))
        await db.commit()
        return dict(row)


async def is_in_waitlist(telegram_id: int) -> bool:
    """Есть ли пользователь в листе ожидания."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM waitlist WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def clear_old_waitlist(days: int = 30):
    """Удалить из листа ожидания тех, кто ждёт больше N дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM waitlist
            WHERE created_at < datetime('now', ?)
        """, (f'-{days} days',))
        await db.commit()


# ============================================================
# ЛИМИТ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

async def count_active_users() -> int:
    """Сколько пользователей со статусом 'active'."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE status = 'active'"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def is_limit_reached(max_users: int) -> bool:
    """Достигнут ли лимит активных пользователей."""
    if max_users <= 0:
        return False
    count = await count_active_users()
    return count >= max_users


# ============================================================
# СЧЁТЧИК ПРОДЛЕНИЙ
# ============================================================

async def increment_renew_count(telegram_id: int) -> int:
    """Увеличить счётчик продлений. Возвращает новое значение."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET renew_count = COALESCE(renew_count, 0) + 1
            WHERE telegram_id = ?
        """, (telegram_id,))
        await db.commit()

        async with db.execute(
            "SELECT renew_count FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

# ============================================================
# ВЕБ-ПРИВЯЗКА (для /start link_<token>)
# ============================================================

async def get_invite_link_any(token: str):
    """Найти invite_link по токену БЕЗ фильтра is_used/7 дней.
    Используется для привязки веб-юзера к Telegram.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM invite_links WHERE token = ?", (token,)
        ) as cur:
            return await cur.fetchone()


async def mark_invite_counted(token: str) -> bool:
    """Пометить, что приглашение по этой ссылке засчитано.
    Возвращает True, если пометка установлена (не была установлена раньше).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE invite_links SET counted = 1 WHERE token = ? AND counted = 0",
            (token,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def bind_web_user_to_telegram(
    token: str,
    telegram_id: int,
    username: str,
    first_name: str,
) -> int | None:
    """Создать запись в users для веб-юзера, привязавшегося к боту.

    Возвращает telegram_id созданного пользователя или None, если привязка невозможна:
      - ссылка не найдена
      - ссылка не активирована (is_used=0)
      - ссылка уже привязана к другому TG
      - пользователь уже есть в users
    """
    link = await get_invite_link_any(token)
    if not link:
        return None
    if not link["is_used"]:
        return None
    if link["bound_to_tg_id"] is not None:
        return None

    # Проверим, что такого пользователя ещё нет в users
    existing = await get_user(telegram_id)
    if existing:
        return None

    # expires_at: used_at + 30 дней (как при активации на сайте)
    from datetime import datetime, timedelta
    used_at = link["used_at"] or datetime.now().isoformat()
    try:
        used_dt = datetime.fromisoformat(str(used_at).replace(" ", "T"))
    except Exception:
        used_dt = datetime.now()
    expires = used_dt + timedelta(days=SUBSCRIPTION_DAYS)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users
            (telegram_id, username, first_name, xui_email, sub_id,
             status, invited_by, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, datetime('now'), ?)
        """, (
            telegram_id,
            username or "",
            first_name or "",
            link["xui_email"],
            link["sub_id"],
            link["created_by"],
            expires,
        ))
        await db.execute(
            "UPDATE invite_links SET bound_to_tg_id = ?, bound_at = datetime('now') WHERE token = ?",
            (telegram_id, token)
        )
        await db.commit()

    # Обновляем tgId в 3x-ui (если клиент был создан без него)
    try:
        from xui_client import XUIClient
        async with XUIClient() as xui:
            updated = await xui.update_tg_id(link["xui_email"], telegram_id)
            if updated:
                logger.info(f"✅ tgId={telegram_id} обновлён для {link['xui_email']}")
            else:
                logger.warning(f"⚠️ Не удалось обновить tgId для {link['xui_email']}")
    except Exception as e:
        logger.warning(f"Ошибка update_tg_id для {link['xui_email']}")

    return telegram_id


async def get_abandoned_web_invites(days: int = 30) -> list:
    """Найти веб-выдачи, активированные 30+ дней назад, но не привязанные.

    Использует julianday с коррекцией +3 часа (MSK), потому что
    Flask сохраняет used_at в локальном времени, а SQLite — в UTC.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM invite_links
            WHERE is_used = 1
              AND counted = 1
              AND bound_to_tg_id IS NULL
              AND julianday('now', '+3 hours') - julianday(used_at) >= ?
        """, (days,)) as cur:
            return await cur.fetchall()


# ============================================================
# АВТОПРИВЯЗКА ПО TG ID (без токена)
# ============================================================

async def find_pending_web_link_for_tg(telegram_id: int):
    """Найти активную ссылку, созданную для этого TG (friend_user_id).

    Условия:
      - friend_user_id = telegram_id
      - is_used = 1          (активирована на сайте)
      - bound_to_tg_id IS NULL (ещё не привязана)
      - counted = 1          (приглашение A засчитано)

    Возвращает последнюю (свежую) или None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM invite_links
            WHERE friend_user_id = ?
              AND is_used = 1
              AND counted = 1
              AND bound_to_tg_id IS NULL
            ORDER BY used_at DESC
            LIMIT 1
        """, (telegram_id,)) as cur:
            return await cur.fetchone()

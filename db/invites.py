import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

from .users import get_user

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
                "Переиспользована ссылка %s (created_by=%s, friend_id=%s, friend_username=%s)",
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

async def get_invite_link_any(token: str):
    """Найти invite_link по токену БЕЗ фильтра is_used/срока действия.
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

async def get_expired_web_guests() -> list:
    """Гостевые веб-подписки, срок которых истёк."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT telegram_id, xui_email, sub_id, expires_at, created_at
            FROM users
            WHERE source = 'web'
              AND (telegram_id IS NULL OR telegram_id = 0)
              AND xui_email IS NOT NULL
              AND xui_email != ''
              AND (
                  (expires_at IS NOT NULL AND julianday('now', '+3 hours') >= julianday(expires_at))
                  OR (expires_at IS NULL AND julianday('now') >= julianday(created_at, '+3 days'))
              )
              AND NOT EXISTS (
                  SELECT 1 FROM invite_links il
                  WHERE il.xui_email = users.xui_email
                    AND il.bound_to_tg_id IS NOT NULL
              )
              AND NOT EXISTS (
                  SELECT 1 FROM users u2
                  WHERE u2.xui_email = users.xui_email
                    AND u2.telegram_id IS NOT NULL
                    AND u2.telegram_id != 0
              )
        """) as cur:
            return [dict(row) for row in await cur.fetchall()]

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

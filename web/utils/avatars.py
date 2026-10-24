"""Кэш аватарок и обновление имён из Telegram-профиля."""

import asyncio
import base64
import io
import logging
import time
from pathlib import Path

import aiosqlite
import httpx
from PIL import Image, ImageOps

from config import BOT_TOKEN, DB_PATH
from telegram_api import call

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
AVATAR_DIR = ROOT / "data" / "avatars"
CHECK_TTL = 7 * 24 * 60 * 60
AVATAR_SIZE = 96


def _ensure_dir() -> None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def _avatar_path(tg_id: int) -> Path:
    return AVATAR_DIR / f"{int(tg_id)}.jpg"


def _marker_path(tg_id: int) -> Path:
    return AVATAR_DIR / f"{int(tg_id)}.checked"


def _checked_recently(tg_id: int) -> bool:
    marker = _marker_path(tg_id)
    try:
        return marker.is_file() and (time.time() - marker.stat().st_mtime) < CHECK_TTL
    except OSError:
        return False


def _touch_marker(tg_id: int) -> None:
    _ensure_dir()
    try:
        _marker_path(tg_id).touch()
    except OSError:
        logger.warning("Не удалось сохранить отметку аватарки для %s", tg_id)


def get_avatar_data_url(tg_id: int) -> str:
    """Вернуть data URL аватарки из кэша или пустую строку."""
    if not tg_id:
        return ""
    path = _avatar_path(tg_id)
    try:
        if not path.is_file():
            return ""
        payload = path.read_bytes()
        if not payload:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")
    except OSError:
        return ""


async def refresh_profile(tg_id: int) -> bool:
    """Обновить имя и username из Telegram, не затирая пустыми значениями."""
    chat = await call(BOT_TOKEN, "getChat", chat_id=int(tg_id))
    if not chat:
        return False

    first_name = (chat.get("first_name") or "").strip()
    username = (chat.get("username") or "").strip()
    if first_name in ("", "@"):
        first_name = ""

    if not first_name and not username:
        return False

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                UPDATE users
                SET first_name = COALESCE(NULLIF(?, ''), first_name),
                    username = COALESCE(NULLIF(?, ''), username)
                WHERE telegram_id = ?
                """,
                (first_name, username, int(tg_id)),
            )
            await db.commit()
        return True
    except Exception:
        logger.exception("Не удалось обновить профиль %s", tg_id)
        return False


async def refresh_avatar(tg_id: int, force: bool = False) -> bool:
    """Скачать и сохранить аватарку 96x96. Отсутствие фото кэшируется на неделю."""
    tg_id = int(tg_id)
    if not tg_id:
        return False
    if not force and _checked_recently(tg_id):
        return False

    photos = await call(BOT_TOKEN, "getUserProfilePhotos", user_id=tg_id, limit=1, offset=0)
    if photos is None:
        return False

    sizes = (photos.get("photos") or [None])[0]
    if not sizes:
        _touch_marker(tg_id)
        return False

    chosen = None
    for size in sizes:
        if int(size.get("width") or 0) >= 128:
            chosen = size
            break
    chosen = chosen or sizes[-1]

    file_info = await call(BOT_TOKEN, "getFile", file_id=chosen.get("file_id"))
    file_path = (file_info or {}).get("file_path")
    if not file_path:
        return False

    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.content
    except httpx.HTTPError:
        logger.warning("Не удалось скачать аватарку %s", tg_id)
        return False

    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
        _ensure_dir()
        path = _avatar_path(tg_id)
        tmp = path.with_suffix(".tmp")
        image.save(tmp, "JPEG", quality=86, optimize=True)
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        _touch_marker(tg_id)
        return True
    except Exception:
        logger.exception("Не удалось обработать аватарку %s", tg_id)
        return False


async def refresh_user(tg_id: int) -> None:
    await refresh_profile(int(tg_id))
    await refresh_avatar(int(tg_id))


async def refresh_user_avatars() -> None:
    """Обновить профили и аватарки всех Telegram-пользователей."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL AND telegram_id > 0"
            ) as cur:
                rows = await cur.fetchall()
    except Exception:
        logger.exception("Не удалось прочитать пользователей для аватарок")
        return

    updated = 0
    for (tg_id,) in rows:
        await refresh_user(int(tg_id))
        updated += 1
        await asyncio.sleep(0.05)
    logger.info("Профили и аватарки обновлены: %s", updated)

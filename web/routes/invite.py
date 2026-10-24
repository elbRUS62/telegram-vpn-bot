"""Роуты приглашений (веб-выдача)."""

import logging
import uuid
from datetime import datetime, timedelta

import aiosqlite
from flask import Blueprint, jsonify, render_template, request

from config import BOT_NAME, BOT_USERNAME, BOT_TOKEN, DB_PATH, WEB_SUBSCRIPTION_DAYS
from permissions import get_admin_ids
from database import get_user, use_invite_link, get_invite_link_any
from text_utils import sanitize_email
from xui_client import XUIClient
from web.utils.async_helper import run_async

invite_bp = Blueprint('invite', __name__)
logger = logging.getLogger(__name__)


def _make_qr_base64(data: str) -> str:
    """Генерирует QR-код в base64 (PNG)."""
    import base64
    import io
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


async def notify_admin_new_web_user(friend_username, telegram_id, inviter_id, sub_url):
    from telegram_api import call as tg_call

    text = (
        f"<b>Новый пользователь (веб-выдача)</b>\n\n"
        f"@{friend_username or 'без username'}\n"
        f"<code>{telegram_id}</code>\n"
        f"Пригласил: <code>{inviter_id}</code>\n\n"
        f"{sub_url}"
    )
    for admin_id in get_admin_ids():
        result = await tg_call(
            BOT_TOKEN,
            "sendMessage",
            chat_id=admin_id,
            text=text,
            parse_mode="HTML",
            disable_notification=True,
        )
        if result is None:
            logger.warning("Не удалось отправить уведомление админу %s", admin_id)


@invite_bp.route('/invite/<token>')
def invite_page(token):
    invite = run_async(get_invite_link_any(token))
    if not invite:
        return render_template('error.html',
            message="Ссылка недействительна или уже использована"), 404

    inviter = run_async(get_user(invite["created_by"]))
    inviter_name = "друг"
    if inviter:
        if inviter["username"]:
            inviter_name = f"@{inviter['username']}"
        elif inviter["first_name"]:
            inviter_name = inviter["first_name"]

    return render_template('invite.html',
        token=token,
        inviter_name=inviter_name,
        friend_username=invite["friend_username"] or "друг",
        bot_username=BOT_USERNAME or "skrepnet_bot")


@invite_bp.route('/api/invite/<token>/status', methods=['GET'])
def invite_status(token):
    """Проверяет, использована ли ссылка. Если да — возвращает QR и ссылку."""
    async def check():
        invite = await get_invite_link_any(token)
        if not invite:
            return {'error': 'Ссылка недействительна'}
        
        if not invite["is_used"]:
            return {'used': False}
        
        # Ссылка использована — получаем подписку
        email = invite["xui_email"]
        if not email:
            return {'used': True, 'error': 'Подписка не найдена'}
        
        try:
            async with XUIClient() as xui:
                client = await xui.get_client(email)
                if not client:
                    return {'used': True, 'error': 'Клиент не найден'}
                sub_id = client.get("subId")
                if not sub_id:
                    return {'used': True, 'error': 'Sub ID не найден'}
                sub_url = xui.build_sub_url(sub_id)
                
                qr_base64 = _make_qr_base64(sub_url)
                
                return {
                    'used': True,
                    'sub_url': sub_url,
                    'qr_base64': qr_base64,
                    'email': email,
                    'message': 'Вы уже получили подписку по этой ссылке'
                }
        except Exception as e:
            return {'used': True, 'error': 'Внутренняя ошибка сервера'}
    
    result = run_async(check())
    if 'error' in result and not result.get('used'):
        return jsonify(result), 404
    return jsonify(result)

@invite_bp.route('/api/activate/<token>', methods=['POST'])
def activate(token):
    data = request.json or {}
    if not data.get('accepted_terms'):
        return jsonify({'error': 'Необходимо принять условия'}), 400

    async def process():
        invite = await get_invite_link_any(token)
        if not invite:
            return {'error': 'Ссылка недействительна'}

        # Защита от активации просроченных неиспользованных ссылок.
        if not invite["is_used"]:
            created = invite["created_at"]
            try:
                created_dt = datetime.strptime(str(created), "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                return {'error': 'Ссылка недействительна'}
            if datetime.now() - created_dt > timedelta(days=WEB_SUBSCRIPTION_DAYS):
                return {'error': 'Срок действия ссылки истёк', 'expired': True}

        # Если ссылка уже использована — не выходим, идём в общий путь:
        # update_expiry продлит существующего клиента (+3 дня),
        # add_client создаст нового, если в 3x-ui его почему-то нет.
        # sub_id не меняется, гость получит тот же QR.

        # Приоритет: @username > ID > fallback (guest_...)
        if invite["friend_username"]:
            name = invite["friend_username"]
        elif invite["friend_user_id"]:
            name = str(invite["friend_user_id"])
        else:
            name = f"guest_{invite['created_by']}_{uuid.uuid4().hex[:8]}"

        telegram_id = invite["friend_user_id"] or 0
        xui_email = sanitize_email(name, telegram_id)

        # Гостевая ссылка не продлевает подписку повторно:
        # если она уже активирована — просто отдаём существующий доступ.
        if invite["is_used"]:
            try:
                async with XUIClient() as xui:
                    existing = await xui.get_client(xui_email)
                    sub_id = existing.get("subId")
                    if not sub_id:
                        return {'error': 'Подписка не найдена'}
                    sub_url = xui.build_sub_url(sub_id)
            except Exception:
                logger.exception("Ошибка получения существующей веб-подписки")
                return {'error': 'Подписка не найдена'}

            return {
                'sub_url': sub_url,
                'sub_id': sub_id,
                'email': xui_email,
                'qr_base64': _make_qr_base64(sub_url),
            }

        expires_at_db = datetime.now() + timedelta(days=WEB_SUBSCRIPTION_DAYS)

        try:
            async with XUIClient() as xui:
                auto_comment = "Гость без Telegram"

                # B уже в 3x-ui?  продлить (+3 дня), отдать ссылку; иначе создать
                try:
                    existing = await xui.get_client(xui_email)
                    has_client = True
                except Exception:
                    has_client = False

                if has_client:
                    # Жестко ограничиваем срок: ровно 3 дня от текущего момента.
                    current_expiry = existing.get("expiryTime", 0)
                    now_ms = int(datetime.now().timestamp() * 1000)
                    target_expiry = now_ms + (WEB_SUBSCRIPTION_DAYS * 24 * 60 * 60 * 1000)
                    expires_at_db = datetime.fromtimestamp(target_expiry / 1000)

                    # Если разница с целевым больше 1 минуты — обновляем (урезаем или продлеваем)
                    if abs(current_expiry - target_expiry) > 60_000:
                        payload = {
                            "email": xui_email,
                            "expiryTime": target_expiry,
                            "limitIp": existing.get("limitIp", 3),
                            "enable": True,
                            "totalGB": 0,
                            "comment": existing.get("comment", "") or auto_comment,
                            "subId": existing.get("subId", ""),
                            "group": existing.get("group", ""),
                            "tgId": existing.get("tgId", 0)
                        }
                        res = await xui._post(f"/panel/api/clients/update/{xui_email}", payload)
                        if not res.get("success"):
                            logger.warning("Ошибка обновления клиента %s: %s", xui_email, res)
                        else:
                            logger.info(f"Срок зафиксирован ровно на {WEB_SUBSCRIPTION_DAYS} дн. {xui_email}")
                    else:
                        logger.info(f"Срок {xui_email} уже ровно {WEB_SUBSCRIPTION_DAYS} дн.")

                    sub_id = existing.get("subId")
                    sub_url = xui.build_sub_url(sub_id)
                    logger.info(f"Продлён существующий {xui_email} (+{WEB_SUBSCRIPTION_DAYS} дн.)")
                else:
                    sub_id = await xui.add_client(
                        xui_email,
                        days=WEB_SUBSCRIPTION_DAYS,
                        comment=auto_comment,
                        tg_id=invite["friend_user_id"] or 0,
                        group=BOT_NAME,
                    )
                    sub_url = xui.build_sub_url(sub_id)
                    logger.info(f"Создан новый {xui_email} ({WEB_SUBSCRIPTION_DAYS} дн.)")
        except Exception as e:
            logger.exception("Ошибка создания клиента (email=%s)", xui_email)
            return {'error': 'Внутренняя ошибка сервера'}

        await use_invite_link(token, xui_email, sub_id)

        # Создаём запись в users для ЛЮБОГО гостя (включая без TG, telegram_id=NULL)
        # Ищем существующего: по telegram_id (если есть) или по xui_email (повторная выдача)
        existing = None
        if invite["friend_user_id"]:
            existing = await get_user(invite["friend_user_id"])

        if not existing:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT telegram_id FROM users WHERE xui_email = ?",
                    (xui_email,),
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        existing = {"telegram_id": row[0]}

        if existing:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET expires_at = ?, status = 'active'"
                    " WHERE xui_email = ?",
                    (expires_at_db.strftime("%Y-%m-%d %H:%M:%S"), xui_email),
                )
                await db.commit()
        else:
            tg_id_for_db = invite["friend_user_id"]  # может быть None
            username_for_db = invite["friend_username"] or ""
            if invite["friend_username"]:
                first_name_for_db = invite["friend_username"]
            elif invite["friend_user_id"]:
                first_name_for_db = f"guest_{invite['friend_user_id']}"
            else:
                first_name_for_db = "Гость (веб)"

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO users
                        (telegram_id, username, first_name, xui_email,
                         status, sub_id, source, expires_at)
                    VALUES (?, ?, ?, ?, 'active', ?, 'web', ?)
                """, (
                    tg_id_for_db,
                    username_for_db,
                    first_name_for_db,
                    xui_email,
                    sub_id,
                    expires_at_db.strftime("%Y-%m-%d %H:%M:%S"),
                ))
                await db.commit()
            logger.info(
                f"Создан пользователь в БД: tg_id={tg_id_for_db}, "
                f"first_name={first_name_for_db!r} ({xui_email}) source=web"
            )

        try:
            from database import mark_invite_counted, increment_invites, add_invite
            counted = await mark_invite_counted(token)
            if counted:
                await increment_invites(invite["created_by"])
                await add_invite(
                    inviter_id=invite["created_by"],
                    invited_user_id=invite["friend_user_id"],
                    invited_username=invite["friend_username"],
                    invited_first_name=None,
                    invite_type="no_tg",
                )
        except Exception as e:
            logger.exception("Ошибка засчёта приглашения (token=%s)", token)

        qr_base64 = _make_qr_base64(sub_url)

        return {
            'sub_url': sub_url,
            'sub_id': sub_id,
            'email': xui_email,
            'qr_base64': qr_base64
        }

    result = run_async(process())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)

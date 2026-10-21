"""Роуты приглашений (веб-выдача)."""

import logging
from datetime import datetime, timedelta

import aiosqlite
from flask import Blueprint, jsonify, render_template, request

from config import BOT_NAME, ADMIN_IDS, BOT_TOKEN, DB_PATH, SUBSCRIPTION_DAYS, WEB_SUBSCRIPTION_DAYS
from database import get_invite_link, get_user, use_invite_link, get_invite_link_any
from handlers.utils import sanitize_email
from xui_client import XUIClient
from web.utils.async_helper import run_async

invite_bp = Blueprint('invite', __name__)
logger = logging.getLogger(__name__)


async def notify_admin_new_web_user(friend_username, telegram_id, inviter_id, sub_url):
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        text = (
            f"🆕 <b>Новый пользователь (веб-выдача)</b>\n\n"
            f"👤 @{friend_username or 'без username'}\n"
            f"🆔 <code>{telegram_id}</code>\n"
            f"👥 Пригласил: <code>{inviter_id}</code>\n\n"
            f"🔗 {sub_url}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, disable_notification=True)
            except Exception as e:
                logger.exception("Ошибка отправки админу %s", admin_id)
    finally:
        await bot.session.close()


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
        friend_username=invite["friend_username"] or "друг")


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
                
                # Генерируем QR
                import base64, io, qrcode
                qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
                qr.add_data(sub_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                qr_base64 = base64.b64encode(buf.read()).decode('utf-8')
                
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

        # Защита от активации просроченных (старше 7 дней) неиспользованных ссылок.
        # Использованные ссылки не проверяем — по ним отдаём QR (повторный клик).
        if not invite["is_used"]:
            created = invite["created_at"]
            try:
                created_dt = datetime.strptime(str(created), "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                return {'error': 'Ссылка недействительна'}
            if datetime.now() - created_dt > timedelta(days=7):
                return {'error': 'Срок действия ссылки истёк', 'expired': True}

        # Если ссылка уже использована — возвращаем существующую подписку
        if invite["is_used"]:
            # Получаем подписку из 3x-ui по email
            email = invite["xui_email"]
            if not email:
                return {'error': 'Подписка не найдена', 'used': True}
            
            try:
                async with XUIClient() as xui:
                    client = await xui.get_client(email)
                    if not client:
                        return {'error': 'Клиент не найден в 3x-ui', 'used': True}
                    sub_id = client.get("subId")
                    if not sub_id:
                        return {'error': 'Sub ID не найден', 'used': True}
                    sub_url = xui.build_sub_url(sub_id)
                    
                    # Генерируем QR
                    import base64, io, qrcode
                    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
                    qr.add_data(sub_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    qr_base64 = base64.b64encode(buf.read()).decode('utf-8')
                    
                    return {
                        'used': True,
                        'sub_url': sub_url,
                        'qr_base64': qr_base64,
                        'email': email,
                        'message': 'Вы уже получили подписку по этой ссылке'
                    }
            except Exception as e:
                return {'error': 'Внутренняя ошибка сервера', 'used': True}

        # Приоритет: @username > ID > fallback (guest_...)
        if invite["friend_username"]:
            name = invite["friend_username"]
        elif invite["friend_user_id"]:
            name = str(invite["friend_user_id"])
        else:
            name = f"guest_{invite['created_by']}_{int(datetime.now().timestamp())}"

        telegram_id = invite["friend_user_id"] or 0
        xui_email = sanitize_email(name, telegram_id)

        try:
            async with XUIClient() as xui:
                user_part = f"@{invite['friend_username']}" if invite["friend_username"] else "guest"
                inviter_part = str(invite['created_by'])
                if invite['created_by']:
                    inviter = await get_user(invite['created_by'])
                    if inviter and inviter['username']:
                        inviter_part = f"@{inviter['username']}"

                auto_comment = f"{user_part} | web → bot | от: {inviter_part}"

                # B уже в 3x-ui? → продлить (+3 дня), отдать ссылку; иначе создать
                try:
                    existing = await xui.get_client(xui_email)
                    has_client = True
                except Exception:
                    has_client = False

                if has_client:
                    await xui.update_expiry(xui_email, days=WEB_SUBSCRIPTION_DAYS)
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

        # Создаём запись в users (чтобы гость появился в админке)
        if invite["friend_user_id"]:
            existing = await get_user(invite["friend_user_id"])
            if not existing:
                import aiosqlite
                from config import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("""
                        INSERT OR REPLACE INTO users (telegram_id, username, first_name, xui_email, status, sub_id, source) VALUES (?, ?, ?, ?, 'active', ?, 'web')
                    """, (
                        invite["friend_user_id"],
                        invite["friend_username"] or "",
                        invite["friend_username"] or f"guest_{invite['friend_user_id']}",
                        xui_email,
                        sub_id
                    ))
                    await db.commit()
                logger.info(f"✅ Создан пользователь в БД: {invite['friend_user_id']} ({xui_email})")

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

        try:
            await notify_admin_new_web_user(
                friend_username=invite["friend_username"],
                telegram_id=invite["friend_user_id"] or 0,
                inviter_id=invite["created_by"],
                sub_url=sub_url
            )
        except Exception as e:
            logger.exception("Ошибка уведомления админов о новом веб-пользователе")

        import base64
        import io
        import qrcode

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(sub_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qr_base64 = base64.b64encode(buf.read()).decode('utf-8')

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

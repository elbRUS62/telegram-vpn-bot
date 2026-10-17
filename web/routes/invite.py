"""Роуты приглашений (веб-выдача)."""

import asyncio
import logging
from datetime import datetime

import aiosqlite
from flask import Blueprint, jsonify, render_template, request

from config import ADMIN_IDS, BOT_TOKEN, DB_PATH, SUBSCRIPTION_DAYS
from database import get_invite_link, get_user, use_invite_link
from handlers.utils import sanitize_email
from xui_client import XUIClient

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
                logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    finally:
        await bot.session.close()


@invite_bp.route('/invite/<token>')
def invite_page(token):
    invite = asyncio.run(get_invite_link(token))
    if not invite:
        return render_template('error.html',
            message="Ссылка недействительна или уже использована"), 404

    inviter = asyncio.run(get_user(invite["created_by"]))
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


@invite_bp.route('/api/activate/<token>', methods=['POST'])
def activate(token):
    data = request.json or {}
    if not data.get('accepted_terms'):
        return jsonify({'error': 'Необходимо принять условия'}), 400

    async def process():
        invite = await get_invite_link(token)
        if not invite:
            return {'error': 'Ссылка недействительна'}

        if invite["friend_username"]:
            name = invite["friend_username"]
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

                sub_id = await xui.add_client(
                    xui_email,
                    days=SUBSCRIPTION_DAYS,
                    comment=auto_comment,
                    tg_id=invite["friend_user_id"] or 0,
                )
                sub_url = xui.build_sub_url(sub_id)
        except Exception as e:
            logger.error(f"Ошибка создания клиента: {e}")
            return {'error': f'Ошибка создания подписки: {e}'}

        await use_invite_link(token, xui_email, sub_id)

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
            logger.error(f"Ошибка засчёта приглашения: {e}")

        try:
            await notify_admin_new_web_user(
                friend_username=invite["friend_username"],
                telegram_id=invite["friend_user_id"] or 0,
                inviter_id=invite["created_by"],
                sub_url=sub_url
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")

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

    result = asyncio.run(process())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)

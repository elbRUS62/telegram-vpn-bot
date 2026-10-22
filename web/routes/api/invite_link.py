import base64
import io

import qrcode
from flask import jsonify, request

from config import WEB_BASE_URL
from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api, logger

# Создание ссылки для друга без Telegram
# ============================================================

@api.route('/create_invite_link', methods=['POST'])
def create_link_for_friend():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')
    friend_input = data.get('friend_input', '').strip()

    async def do_create():
        from database import get_user, create_invite_link
        
        # Проверяем, что пользователь активен
        db_user = await get_user(telegram_id)
        if not db_user or db_user["status"] != "active":
            return {'error': 'Сначала получи подписку'}

        friend_username = None
        friend_id = None
        
        if friend_input:
            if friend_input.startswith("@"):
                friend_username = friend_input.lstrip("@")
            elif friend_input.isdigit():
                friend_id = int(friend_input)
            else:
                friend_username = friend_input

        # Создаём токен (функция из database.py)
        token = await create_invite_link(
            telegram_id=telegram_id,
            friend_user_id=friend_id,
            friend_username=friend_username
        )

        # Формируем ссылку на наш сайт
        base_url = f"{WEB_BASE_URL.rstrip('/')}/invite/"
        invite_url = f"{base_url}{token}"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(invite_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            'success': True,
            'invite_url': invite_url,
            'qr_base64': qr_base64,
            'friend_name': friend_input if friend_input else "гостевой доступ"
        }

    result = run_async(do_create())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================

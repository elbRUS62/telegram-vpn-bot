from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api

# Рефералка
# ============================================================

@api.route('/referral', methods=['POST'])
def referral():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')

    async def get_data():
        from config import BOT_USERNAME
        from database import get_user, get_top_inviters

        db_user = await get_user(telegram_id)
        if not db_user:
            return {'error': 'Сначала получи подписку'}

        invites = db_user["invites_count"] or 0
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{telegram_id}"

        top = await get_top_inviters(5)
        top_list = []
        for inv in top:
            inv_user = await get_user(inv["inviter_id"])
            name = "—"
            if inv_user:
                if inv_user["username"]:
                    name = f"@{inv_user['username']}"
                elif inv_user["first_name"]:
                    name = inv_user["first_name"]
            top_list.append({'name': name, 'total': inv["total"]})

        return {
            'ref_link': ref_link,
            'invites_count': invites,
            'top_inviters': top_list,
        }

    result = run_async(get_data())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================

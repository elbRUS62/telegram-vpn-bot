from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api

# Главная
# ============================================================

@api.route('/main', methods=['POST'])
def main():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')
    if not telegram_id:
        return jsonify({'error': 'Нет ID'}), 400

    async def get_data():
        from config import BOT_NAME, SERVER_COST, SUB_BASE_URL, SUB_PATH
        from database import get_user, get_donations_total, get_support_unread_count
        from permissions import get_admin_summary
        from datetime import datetime

        db_user = await get_user(telegram_id)
        admin = get_admin_summary(telegram_id)
        support_unread = await get_support_unread_count(telegram_id)

        if not db_user:
            status, status_text, has_sub = 'new', 'Нет подписки', False
        elif db_user['status'] == 'active':
            status, status_text, has_sub = 'active', 'Подписка активна', True
        elif db_user['status'] == 'pending':
            status, status_text, has_sub = 'pending', 'Заявка на рассмотрении', False
        elif db_user['status'] == 'rejected':
            status, status_text, has_sub = 'rejected', 'Заявка отклонена', False
        else:
            status, status_text, has_sub = db_user['status'], db_user['status'], False

        donated = await get_donations_total(currency="RUB")
        percent = min(int(donated / SERVER_COST * 100), 100) if SERVER_COST > 0 else 0

        months = ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
        next_month_idx = datetime.now().month % 12
        next_month_name = months[next_month_idx]

        return {
            'first_name': user.get('first_name', 'друг'),
            'username': user.get('username', ''),
            'status': status,
            'status_text': status_text,
            'has_subscription': has_sub,
            'is_admin': admin["is_admin"],
            'is_superadmin': admin["is_superadmin"],
            'admin_role': admin["role"],
            'progress_percent': percent,
            'donated': int(donated),
            'server_cost': SERVER_COST,
            'bot_name': BOT_NAME,
            'next_month': next_month_name,
            'support_unread': support_unread,
            'sub_url': f"{SUB_BASE_URL}{SUB_PATH}{db_user['sub_id']}" if has_sub and db_user['sub_id'] else '',
        }

    result = run_async(get_data())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================

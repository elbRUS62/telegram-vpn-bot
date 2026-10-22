from datetime import datetime

from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api

# Донат
# ============================================================

@api.route('/donate', methods=['POST'])
def donate():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    async def get_data():
        from config import DONATE_TEXT, DONATE_URL, SERVER_COST
        from database import get_donations_total

        donated = await get_donations_total(currency="RUB")
        percent = min(int(donated / SERVER_COST * 100), 100) if SERVER_COST > 0 else 0

        months = ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]
        next_month_idx = datetime.now().month % 12
        next_month_name = months[next_month_idx]

        return {
            'donate_text': DONATE_TEXT,
            'donate_url': DONATE_URL,
            'progress_percent': percent,
            'server_cost': SERVER_COST,
            'donated': int(donated),
            'next_month': next_month_name,
        }

    result = run_async(get_data())
    return jsonify(result)


# ============================================================

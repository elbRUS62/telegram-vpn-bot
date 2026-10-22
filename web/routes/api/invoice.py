from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api, logger

# Инвойс для оплаты звёздами внутри Mini App
# ============================================================

@api.route('/invoice', methods=['POST'])
def create_invoice():
    from config import BOT_TOKEN, BOT_NAME

    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    amount = data.get('amount', 10)  # По умолчанию 10 звёзд

    async def send_invoice():
        from telegram_api import call as tg_call

        # Создаём ссылку на инвойс (без отправки сообщения пользователю)
        return await tg_call(
            BOT_TOKEN,
            "createInvoiceLink",
            title=f"Поддержка {BOT_NAME} · {amount} ⭐",
            description=f"Донат {amount} ⭐ на оплату сервера и развитие проекта. Спасибо за поддержку!",
            payload=f"donate_miniapp_{user.get('id')}_{amount}",
            provider_token="",
            currency="XTR",
            prices=[{"label": f"Поддержка {BOT_NAME}", "amount": amount}],
        )

    try:
        link = run_async(send_invoice())
        if not link:
            return jsonify({'error': 'Не удалось создать инвойс'}), 500
        return jsonify({'invoice_link': link})
    except Exception as e:
        logger.error("Invoice error")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


# ============================================================

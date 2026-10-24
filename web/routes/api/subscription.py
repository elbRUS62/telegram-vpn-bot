import base64
import io
from datetime import datetime

import qrcode
from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data
from web.utils.subscription_days import days_left_from_expiry, plan_days_for_source

from .common import api, logger

# Моя подписка
# ============================================================

@api.route('/subscription', methods=['POST'])
def subscription():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')

    async def get_data():
        from database import get_user
        from xui_client import XUIClient

        db_user = await get_user(telegram_id)
        if not db_user or db_user["status"] != "active":
            return {'error': 'Нет активной подписки'}

        try:
            async with XUIClient() as xui:
                sub_url = xui.build_sub_url(db_user["sub_id"])
                client = await xui.get_client(db_user["xui_email"])

                expiry = client.get("expiryTime", 0)
                if expiry > 0:
                    exp_dt = datetime.fromtimestamp(expiry / 1000)
                    exp_date = exp_dt.strftime("%d.%m.%Y")
                    days_left = days_left_from_expiry(exp_dt)

                    if days_left < 0:
                        status_text, status = f"Истекла {exp_date}", "expired"
                    elif days_left <= 3:
                        status_text, status = f"Истекает через {days_left} дн.", "expiring"
                    else:
                        status_text, status = f"Активна до {exp_date}", "active"
                else:
                    exp_date, days_left = "∞", 999
                    status_text, status = "Бессрочно", "active"

                # Получаем трафик через новый эндпоинт
                traffic_data = await xui.get_client_traffic(db_user["xui_email"])
                traffic_up = traffic_data.get("up", 0)
                traffic_down = traffic_data.get("down", 0)
                if traffic_up is not None:
                    traffic_up = traffic_up / (1024**3)
                if traffic_down is not None:
                    traffic_down = traffic_down / (1024**3)
                
                # Проверяем онлайн внутри сессии
                is_online = await xui.is_client_online(db_user["xui_email"])

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

            # Проверяем, онлайн ли клиент
            # Проверяем, что в списке онлайн

            logger.info(f"subscription: is_online для {db_user['xui_email']} = {is_online}")

            return {
                'sub_url': sub_url,
                'expires_at': exp_date,
                'days_left': days_left,
                'plan_days': plan_days_for_source(db_user["source"]),
                'status': status,
                'status_text': status_text,
                'traffic_up': f"{traffic_up:.2f} GB" if traffic_up is not None else "—",
                'traffic_down': f"{traffic_down:.2f} GB" if traffic_down is not None else "—",
                'qr_base64': qr_base64,
                'is_online': is_online,
                'first_name': user.get('first_name', 'Пользователь'),
                'username': user.get('username', ''),
            }
        except Exception as e:
            logger.error("Subscription error")
            return {'error': 'Внутренняя ошибка сервера'}

    result = run_async(get_data())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================

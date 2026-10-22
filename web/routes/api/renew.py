from datetime import datetime, timedelta

from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api, logger

# Продление
# ============================================================

@api.route('/renew', methods=['POST'])
def renew():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')

    async def do_renew():
        from database import get_user, renew_user, increment_renew_count
        from xui_client import XUIClient

        db_user = await get_user(telegram_id)
        if not db_user or db_user["status"] != "active":
            return {'error': 'Нет активной подписки'}

        try:
            async with XUIClient() as xui:
                # Получаем текущую дату окончания
                client = await xui.get_client(db_user["xui_email"])
                current_expiry = client.get("expiryTime", 0) / 1000  # в секундах
                current_dt = datetime.fromtimestamp(current_expiry) if current_expiry > 0 else datetime.now()
                
                today = datetime.now()
                max_allowed = today + timedelta(days=30)
                
                # Если текущая дата уже больше, чем через 30 дней от сегодня — продлевать некуда
                if current_dt > max_allowed:
                    return {'error': 'Подписка уже продлена на максимальный срок (30 дней)'}
                
                # Вычисляем, сколько дней не хватает до максимума
                days_to_add = (max_allowed - current_dt).days
                if days_to_add <= 0:
                    return {'error': 'Подписка уже продлена на максимальный срок (30 дней)'}
                
                # Продлеваем ровно на столько дней, чтобы достичь max_allowed
                new_expiry = await xui.update_expiry(db_user["xui_email"], days=days_to_add)
                new_count = await increment_renew_count(telegram_id)
                date_str = new_expiry.strftime("%d.%m.%Y")

                user_part = f"@{db_user['username']}" if db_user["username"] else str(telegram_id)
                base_comment = f"{user_part} | бот"
                comment = f"{base_comment} | продлён ×{new_count} ({date_str})"

                try:
                    await xui.update_comment(db_user["xui_email"], comment)
                except Exception:
                    pass

            await renew_user(telegram_id, new_expires=new_expiry)

            return {
                'success': True,
                'new_expires_at': new_expiry.strftime("%d.%m.%Y"),
                'days_added': 30,
            }
        except Exception as e:
            logger.error("Renew error")
            return {'error': 'Внутренняя ошибка сервера'}

    result = run_async(do_renew())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================

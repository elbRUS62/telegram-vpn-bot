from permissions import get_admin_ids
from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api, logger

# Принятие соглашения и создание заявки (из Mini App)
# ============================================================

@api.route('/accept_terms', methods=['POST'])
def accept_terms():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    telegram_id = user.get('id')
    
    async def process():
        from database import get_user, create_user_request, approve_user, is_limit_reached
        from config import MAX_USERS
        from text_utils import sanitize_email
        from xui_client import XUIClient
        from config import DONATE_TEXT, BOT_TOKEN
        
        db_user = await get_user(telegram_id)
        
        if db_user and db_user["status"] == "active":
            return {'error': 'У тебя уже есть активная подписка'}
            
        if db_user and db_user["status"] == "pending":
            return {'error': 'Заявка уже отправлена. Жди одобрения.'}

        if await is_limit_reached(MAX_USERS):
            return {'error': 'Достигнут лимит пользователей. Встань в лист ожидания.'}

        name = user.get('username') or user.get('first_name') or f"user{telegram_id}"
        xui_email = sanitize_email(name, telegram_id)
        invited_by = db_user["invited_by"] if db_user else None
        is_referral = invited_by is not None

        await create_user_request(
            telegram_id,
            user.get('username', ''),
            user.get('first_name', ''),
            xui_email,
            invited_by=invited_by
        )

        if is_referral:
            # Автоодобрение для рефералов
            try:
                async with XUIClient() as xui:
                    auto_comment = f"@{user.get('username')} | ref: {invited_by}" if user.get('username') else f"ID {telegram_id} | ref: {invited_by}"
                    sub_id = await xui.get_or_create_client(xui_email, comment=auto_comment)
                    await approve_user(telegram_id, sub_id)
                    sub_url = xui.build_sub_url(sub_id)
                    
                    return {'success': True, 'type': 'auto_approved'}
            except Exception as e:
                return {'error': 'Ошибка создания подписки'}
        else:
            # Отправляем уведомление админам (без aiogram — через Bot API по HTTP)
            from telegram_api import call as tg_call

            logger.info("Отправка заявки админам для %s", telegram_id)
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "Одобрить", "callback_data": f"approve:{telegram_id}"},
                    {"text": "Отклонить", "callback_data": f"reject:{telegram_id}"},
                ]]
            }
            for admin_id in get_admin_ids():
                result = await tg_call(
                    BOT_TOKEN,
                    "sendMessage",
                    chat_id=admin_id,
                    text=(
                        f"<b>Новая заявка (Mini App)</b>\n\n"
                        f"Пользователь: {user.get('first_name')} @{user.get('username')}\n"
                        f"ID: <code>{telegram_id}</code>\n"
                        f"Email: {xui_email}"
                    ),
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                if result is None:
                    logger.error(f"Ошибка отправки админу {admin_id}")
                else:
                    logger.info(f"Уведомление отправлено админу {admin_id}")

            return {'success': True, 'type': 'pending'}

    result = run_async(process())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)

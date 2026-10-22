"""API-роуты для Mini App."""

import base64
import io
import logging
from datetime import datetime, timedelta

import qrcode
from flask import Blueprint, jsonify, request

from web.utils.auth import validate_init_data
from web.utils.async_helper import run_async
from config import WEB_BASE_URL

logger = logging.getLogger(__name__)

api = Blueprint('miniapp_api', __name__, url_prefix='/api/miniapp')


# ============================================================
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
        from config import ADMIN_IDS, BOT_NAME, SERVER_COST
        from database import get_user, get_donations_total
        from datetime import datetime

        db_user = await get_user(telegram_id)
        is_admin = telegram_id in ADMIN_IDS

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
            'is_admin': is_admin,
            'progress_percent': percent,
            'bot_name': BOT_NAME,
            'next_month': next_month_name
        }

    result = run_async(get_data())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================
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
                    days_left = (exp_dt - datetime.now()).days

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
# Профиль
# ============================================================

@api.route('/profile', methods=['POST'])
def profile():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    from config import BOT_NAME, BOT_VERSION, SUPPORT_USERNAME
    from flask import render_template

    # Читаем HTML-контент документов из шаблонов
    docs_content = {
        "rules": render_template("docs/rules.html"),
        "privacy": render_template("docs/privacy.html"),
        "terms": render_template("docs/terms.html")
    }

    return jsonify({
        'bot_name': BOT_NAME,
        'bot_version': BOT_VERSION,
        'support_username': SUPPORT_USERNAME,
        'documents': [
            {'title': 'Правила использования', 'key': 'rules', 'content': docs_content['rules']},
            {'title': 'Политика конфиденциальности', 'key': 'privacy', 'content': docs_content['privacy']},
            {'title': 'Пользовательское соглашение', 'key': 'terms', 'content': docs_content['terms']},
        ],
    })


# ============================================================
# Устройства (заглушка)
# ============================================================

@api.route('/devices', methods=['POST'])
def devices():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    return jsonify({'devices': []})


# ============================================================
# Платформы (Как подключиться)
# ============================================================

PLATFORMS_INFO = {
    'android': {
        'title': 'Android',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://play.google.com/store/apps/details?id=com.happproxy',
        'steps': [
            'Установи Happ из Google Play',
            'Скопируй ссылку из «Моя подписка»',
            'В Happ: «+» → «Добавить подписку»',
            'Вставь ссылку → сохрани',
            'Выбери сервер → Подключись',
        ],
        'alternatives': 'Hysteria, v2rayNG',
    },
    'ios': {
        'title': 'iOS (iPhone / iPad)',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
        'steps': [
            'Установи Happ из App Store',
            'Скопируй ссылку из «Моя подписка»',
            'В Happ: «+» → «Добавить подписку»',
            'Вставь ссылку → сохрани',
            'Выбери сервер → включи VPN',
        ],
        'alternatives': 'Streisand, Shadowrocket',
        'note': 'Если нет в российском App Store — смени регион Apple ID на США',
    },
    'windows': {
        'title': 'Windows',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Скачай Happ с официального сайта',
            'Скопируй ссылку из «Моя подписка»',
            'В Happ: «+» → «Добавить подписку»',
            'Вставь ссылку → сохрани',
            'Выбери сервер → Подключись',
        ],
        'alternatives': 'Hysteria для Windows',
    },
    'macos': {
        'title': 'macOS',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
        'steps': [
            'Установи Happ из App Store',
            'Скопируй ссылку из «Моя подписка»',
            'В Happ: «+» → «Добавить подписку»',
            'Вставь ссылку → сохрани',
            'Выбери сервер → включи VPN',
        ],
        'alternatives': 'Streisand, Clash Verge',
    },
    'androidtv': {
        'title': 'Android TV',
        'app': 'Happ / v2rayTun',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Способ 1: Установи Happ на телефон, импортируй подписку',
            'Установи v2rayTun на ТВ → «Импорт с телефона»',
            'Отсканируй QR-код',
            'Или: скачай APK Happ на ТВ через Send Files to TV',
            'Выбери сервер → Подключись',
        ],
        'alternatives': 'v2rayTun',
    },
    'linux': {
        'title': 'Linux',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Скачай Happ для Linux (.deb / .rpm / .AppImage)',
            'Установи и запусти',
            'Скопируй ссылку из «Моя подписка»',
            'В Happ: «+» → «Добавить подписку»',
            'Выбери сервер → Подключись',
        ],
        'alternatives': 'Hysteria, Nekoray, Clash Verge',
    },
}


@api.route('/connect', methods=['POST'])
def connect_list():
    return jsonify({
        'platforms': [
            {'key': k, 'title': v['title']}
            for k, v in PLATFORMS_INFO.items()
        ]
    })


@api.route('/connect/<platform>', methods=['POST'])
def connect(platform):
    info = PLATFORMS_INFO.get(platform)
    if not info:
        return jsonify({'error': 'Платформа не найдена'}), 404
    return jsonify(info)


# ============================================================
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

        return {
            'success': True,
            'invite_url': invite_url,
            'friend_name': friend_input if friend_input else "гостевой доступ"
        }

    result = run_async(do_create())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


# ============================================================
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
        from config import ADMIN_IDS, DONATE_TEXT, BOT_TOKEN
        
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
                    sub_id = await xui.add_client(xui_email, comment=auto_comment)
                    await approve_user(telegram_id, sub_id)
                    sub_url = xui.build_sub_url(sub_id)
                    
                    return {'success': True, 'type': 'auto_approved'}
            except Exception as e:
                return {'error': 'Ошибка создания подписки'}
        else:
            # Отправляем уведомление админам (без aiogram — через Bot API по HTTP)
            from telegram_api import call as tg_call

            logger.info(f"Отправка заявки админам {ADMIN_IDS} для {telegram_id}")
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "✅ Одобрить", "callback_data": f"approve:{telegram_id}"},
                    {"text": "❌ Отклонить", "callback_data": f"reject:{telegram_id}"},
                ]]
            }
            for admin_id in ADMIN_IDS:
                result = await tg_call(
                    BOT_TOKEN,
                    "sendMessage",
                    chat_id=admin_id,
                    text=(
                        f"🆕 <b>Новая заявка (Mini App)</b>\n\n"
                        f"👤 {user.get('first_name')} @{user.get('username')}\n"
                        f"🆔 <code>{telegram_id}</code>\n"
                        f"📧 {xui_email}"
                    ),
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                if result is None:
                    logger.error(f"Ошибка отправки админу {admin_id}")
                else:
                    logger.info(f"✅ Уведомление отправлено админу {admin_id}")

            return {'success': True, 'type': 'pending'}

    result = run_async(process())
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)

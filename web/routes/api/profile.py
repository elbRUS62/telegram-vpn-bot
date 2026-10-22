from flask import jsonify, request

from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api

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

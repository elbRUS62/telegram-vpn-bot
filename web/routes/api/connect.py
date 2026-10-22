from flask import jsonify, request

from .common import api

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

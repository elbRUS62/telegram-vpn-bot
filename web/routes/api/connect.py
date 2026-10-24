from flask import jsonify, request

from .common import api

# Платформы (Как подключиться)
# ============================================================

COMMON_TROUBLESHOOTING = [
    'Обновите подписку: в Happ откройте профиль и нажмите «Обновить».',
    'Выберите другой сервер: GB или RU.',
    'Проверьте дату, время и часовой пояс на устройстве.',
    'Если ссылка не добавляется, скопируйте её заново из раздела «Подписка».',
]

PLATFORMS_INFO = {
    'android': {
        'title': 'Android',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://play.google.com/store/apps/details?id=com.happproxy',
        'steps': [
            'Установите Happ из Google Play.',
            'Скопируйте ссылку в разделе «Подписка».',
            'В Happ нажмите «+» и выберите «Добавить подписку».',
            'Вставьте ссылку и сохраните профиль.',
            'Обновите подписку, если список серверов пуст.',
            'Выберите сервер и включите VPN.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Разрешите VPN-подключение в системном запросе.',
            'Отключите экономию батареи для Happ в настройках Android.',
        ],
        'alternatives': 'Hysteria, v2rayNG',
    },
    'ios': {
        'title': 'iOS (iPhone / iPad)',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
        'steps': [
            'Установите Happ из App Store.',
            'Скопируйте ссылку в разделе «Подписка».',
            'В Happ нажмите «+» и выберите «Добавить подписку».',
            'Вставьте ссылку и сохраните профиль.',
            'Обновите подписку, если список серверов пуст.',
            'Выберите сервер и включите VPN.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Разрешите добавление VPN-конфигурации в настройках iOS.',
        ],
        'alternatives': 'Streisand, Shadowrocket',
        'note': 'Если приложения нет в российском App Store, смените регион Apple ID на США.',
    },
    'windows': {
        'title': 'Windows',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Скачайте Happ с официального сайта.',
            'Скопируйте ссылку в разделе «Подписка».',
            'В Happ нажмите «+» и выберите «Добавить подписку».',
            'Вставьте ссылку и сохраните профиль.',
            'Обновите подписку, если список серверов пуст.',
            'Выберите сервер и подключитесь.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Если TUN не поднимается, запустите Happ от имени администратора.',
        ],
        'alternatives': 'Hysteria для Windows',
    },
    'macos': {
        'title': 'macOS',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://apps.apple.com/us/app/happ-proxy-utility/id6504287215',
        'steps': [
            'Установите Happ из App Store.',
            'Скопируйте ссылку в разделе «Подписка».',
            'В Happ нажмите «+» и выберите «Добавить подписку».',
            'Вставьте ссылку и сохраните профиль.',
            'Обновите подписку, если список серверов пуст.',
            'Выберите сервер и включите VPN.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Разрешите системное расширение VPN в настройках безопасности macOS.',
        ],
        'alternatives': 'Streisand, Clash Verge',
    },
    'androidtv': {
        'title': 'Android TV',
        'app': 'Happ / v2rayTun',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Способ 1: установите Happ на телефон и импортируйте подписку.',
            'Установите v2rayTun на телевизор и выберите «Импорт с телефона».',
            'Отсканируйте QR-код.',
            'Или скачайте APK Happ на телевизор через Send Files to TV.',
            'Выберите сервер и подключитесь.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Если клавиатура неудобна, импортируйте подписку по QR-коду с телефона.',
        ],
        'alternatives': 'v2rayTun',
    },
    'linux': {
        'title': 'Linux',
        'app': 'Happ — Proxy Utility',
        'app_url': 'https://www.happ.su/main/',
        'steps': [
            'Скачайте Happ для Linux (.deb, .rpm или .AppImage).',
            'Установите и запустите приложение.',
            'Скопируйте ссылку в разделе «Подписка».',
            'В Happ нажмите «+» и выберите «Добавить подписку».',
            'Вставьте ссылку и сохраните профиль.',
            'Выберите сервер и подключитесь.',
        ],
        'troubleshooting': COMMON_TROUBLESHOOTING + [
            'Для TUN-режима может потребоваться запуск с повышенными правами.',
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

import re
from datetime import datetime, timedelta, timezone

import aiosqlite
from flask import jsonify, request

from config import DB_PATH, DIAGNOSTIC_RETENTION_DAYS
from web.utils.async_helper import run_async
from web.utils.auth import validate_init_data

from .common import api, logger

# Диагностика подключения
# ============================================================

async def _collect_diagnostics(telegram_id):
    import aiohttp

    from config import SUB_BASE_URL, SUB_PATH
    from database import get_user
    from xui_client import XUIClient

    db_user = await get_user(telegram_id)
    if not db_user or db_user["status"] != "active":
        return {'error': 'Нет активной подписки'}

    result = {
        'panel_name': None,
        'panel_ok': False,
        'client_found': False,
        'enabled': False,
        'is_online': False,
        'sub_link_ok': False,
        'sub_http_status': None,
        'checked_at': datetime.now().strftime('%H:%M'),
    }
    sub_url = f"{SUB_BASE_URL}{SUB_PATH}{db_user['sub_id']}"

    try:
        async with XUIClient() as xui:
            result['panel_name'] = xui.panel.get('name') or 'RU'
            result['panel_ok'] = True
            sub_url = xui.build_sub_url(db_user['sub_id'])
            try:
                client = await xui.get_client(db_user['xui_email'])
                result['client_found'] = bool(client)
                result['enabled'] = bool(client.get('enable', False))
            except Exception:
                logger.warning("diagnostics: client not found for %s", telegram_id, exc_info=True)
            result['is_online'] = await xui.is_client_online(db_user['xui_email'])
    except Exception:
        logger.warning("diagnostics: panel unavailable for %s", telegram_id, exc_info=True)

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=6),
            connector=connector,
        ) as session:
            async with session.get(sub_url, allow_redirects=True) as resp:
                result['sub_http_status'] = resp.status
                result['sub_link_ok'] = 200 <= resp.status < 300
    except Exception:
        logger.warning("diagnostics: subscription link check failed for %s", telegram_id, exc_info=True)

    return result


@api.route('/diagnostics', methods=['POST'])
def diagnostics():
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    result = run_async(_collect_diagnostics(user.get('id')))
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


@api.route('/diagnostics/report', methods=['POST'])
def diagnostics_report():
    """Обезличенный агрегат проверки подключения.

    Telegram ID и IP не сохраняются. В базу попадает только час,
    часовой пояс, этап проверки, результат и грубая задержка.
    """
    data = request.json or {}
    user = validate_init_data(data.get('init_data', ''))
    if not user:
        return jsonify({'error': 'Неверная авторизация'}), 401

    allowed_stages = {
        'ok', 'health', 'subscription_link', 'panel',
        'client', 'disabled', 'subscription', 'unknown',
    }
    stage = str(data.get('stage') or 'unknown').strip()
    if stage not in allowed_stages:
        stage = 'unknown'

    timezone_name = str(data.get('timezone') or '').strip()[:64]
    if not re.fullmatch(r'[A-Za-z0-9_+./-]{1,64}', timezone_name):
        timezone_name = 'unknown'

    try:
        latency_ms = max(0, min(60_000, int(data.get('latency_ms') or 0)))
    except (TypeError, ValueError):
        latency_ms = 0
    if latency_ms < 300:
        latency_bucket = '<300'
    elif latency_ms < 1000:
        latency_bucket = '<1000'
    elif latency_ms < 3000:
        latency_bucket = '<3000'
    else:
        latency_bucket = '>=3000'

    now = datetime.now(timezone.utc)
    bucket = now.strftime('%Y-%m-%dT%H:00')
    cutoff = (now - timedelta(days=DIAGNOSTIC_RETENTION_DAYS)).strftime('%Y-%m-%dT%H:00')
    ok = 1 if data.get('ok') is True else 0

    async def store():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM diagnostic_stats WHERE bucket < ?",
                (cutoff,),
            )
            await db.execute("""
                INSERT INTO diagnostic_stats
                    (bucket, timezone, stage, ok, latency_bucket, count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(bucket, timezone, stage, ok, latency_bucket)
                DO UPDATE SET count = count + 1
            """, (bucket, timezone_name, stage, ok, latency_bucket))
            await db.commit()

    try:
        run_async(store())
    except Exception:
        logger.warning("diagnostics report store failed")
        return jsonify({'success': False}), 500

    return jsonify({'success': True})


# ============================================================

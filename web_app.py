"""Flask-приложение для сайта и Mini App."""

import asyncio
import logging
import os
from datetime import timedelta

from flask import Flask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import WEB_ADMIN_SESSION_HOURS, WEB_SECRET_KEY
from database import init_db
from observability import init_sentry
from permissions import seed_admins
from web.routes.docs import docs_bp
from web.routes.health import health_bp
from web.routes.invite import invite_bp
from web.routes.miniapp import miniapp_bp
from web.routes.webadmin import webadmin_bp
from web.routes.api import api
from web.routes.api.admin import admin_api
from web.routes.api.support import support_api

init_sentry("web")

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = WEB_SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=WEB_ADMIN_SESSION_HOURS),
)

# Таблица ролей и перенос ADMIN_ID выполняются и без bot-процесса.
seed_admins()

# Blueprint'ы
app.register_blueprint(health_bp)
app.register_blueprint(invite_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(miniapp_bp)
app.register_blueprint(webadmin_bp)
app.register_blueprint(api)
app.register_blueprint(admin_api)
app.register_blueprint(support_api)


if __name__ == '__main__':
    asyncio.run(init_db())

    from config import SSL_CERT, SSL_KEY, WEB_PORT

    if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        app.run(host='0.0.0.0', port=WEB_PORT, ssl_context=(SSL_CERT, SSL_KEY))
    else:
        logger.warning("SSL сертификаты не найдены — запуск без HTTPS")
        app.run(host='0.0.0.0', port=WEB_PORT)

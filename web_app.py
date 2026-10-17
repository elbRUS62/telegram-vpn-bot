"""Flask-приложение для сайта и Mini App."""

import asyncio
import logging
import os

from flask import Flask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from database import init_db
from web.routes.docs import docs_bp
from web.routes.invite import invite_bp
from web.routes.miniapp import miniapp_bp
from web.routes.api import api

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')

# Blueprint'ы
app.register_blueprint(invite_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(miniapp_bp)
app.register_blueprint(api)


if __name__ == '__main__':
    asyncio.run(init_db())

    SSL_CERT = '/root/cert/gb-skrepnet.duckdns.org/fullchain.pem'
    SSL_KEY = '/root/cert/gb-skrepnet.duckdns.org/privkey.pem'

    if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        app.run(host='0.0.0.0', port=8443, ssl_context=(SSL_CERT, SSL_KEY))
    else:
        logger.warning("SSL сертификаты не найдены — запуск без HTTPS")
        app.run(host='0.0.0.0', port=8443)

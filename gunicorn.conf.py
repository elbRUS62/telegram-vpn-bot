"""Конфигурация gunicorn для сайта и Mini App.

Запуск: venv/bin/gunicorn --config gunicorn.conf.py web_app:app
(так его запускает systemd-сервис skrepnet-web)
"""

import asyncio
import logging
import os

from config import SSL_CERT, SSL_KEY, WEB_PORT

logger = logging.getLogger("gunicorn.skrepnet")

bind = f"0.0.0.0:{WEB_PORT}"

# Сервер: 1 vCPU / 2 GB RAM. Один процесс с потоками — минимум памяти
# и один писатель в SQLite; потоки нужны, потому что роуты синхронные
# и ждут async-хелпер.
workers = int(os.getenv("WEB_WORKERS", "1"))
threads = int(os.getenv("WEB_THREADS", "8"))
worker_class = "gthread"

# Роуты внутри держат до 60 секунд (run_async timeout), даём запас.
timeout = 120
graceful_timeout = 30
keepalive = 5

# Периодическая пересоздание воркера — страховка от утечек памяти.
max_requests = 500
max_requests_jitter = 50

proc_name = "skrepnet-web"
loglevel = os.getenv("WEB_LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(D)sus'

# TLS терминируем прямо в gunicorn — nginx на сервере нет,
# MINIAPP_URL/SUB_BASE_URL указывают на https://<домен>:<порт>.
if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
    certfile = SSL_CERT
    keyfile = SSL_KEY
else:  # pragma: no cover - зависит от сервера
    logger.warning(
        "SSL сертификаты не найдены (%s, %s) — gunicorn запустится без HTTPS",
        SSL_CERT,
        SSL_KEY,
    )


def on_starting(server):
    """Инициализация БД до старта воркеров (раньше это делал web_app.py)."""
    from database import init_db

    asyncio.run(init_db())
    logger.info("База данных инициализирована")

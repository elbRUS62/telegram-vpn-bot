"""Обёртка для запуска async в sync-контексте Flask."""

import asyncio
import logging

logger = logging.getLogger(__name__)


def run_async(coro):
    """Выполнить async-функцию, вернуть результат или {'error': ...}."""
    try:
        return asyncio.run(coro)
    except Exception as e:
        logger.error("Async error: ")
        return {'error': 'Внутренняя ошибка сервера'}

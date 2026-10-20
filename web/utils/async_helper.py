"""Обёртка для запуска async в sync-контексте Flask."""
import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

_loop = asyncio.new_event_loop()
_thread = threading.Thread(target=_loop.run_forever, daemon=True, name="async-helper")
_thread.start()


def run_async(coro):
    """Выполнить async-функцию в общем loop, вернуть результат."""
    try:
        future = asyncio.run_coroutine_threadsafe(coro, _loop)
        return future.result(timeout=60)
    except Exception:
        logger.exception("Async error")
        return {'error': 'Внутренняя ошибка сервера'}

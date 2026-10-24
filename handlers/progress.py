"""Отрисовка прогресса сбора средств на сервер."""

from datetime import datetime

from config import SERVER_COST
from database import get_donations_total


MONTHS_GENITIVE = [
    "январе", "феврале", "марте", "апреле", "мае", "июне",
    "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
]


def _next_month_name() -> str:
    """Название следующего месяца в предложном падеже."""
    now = datetime.now()
    next_month = now.month % 12
    return MONTHS_GENITIVE[next_month]


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


async def render_progress(short: bool = False) -> str:
    """Отрисовать прогресс сбора.

    Args:
        short: если True — короткий текст для напоминаний.
    """
    if SERVER_COST <= 0:
        return ""

    donated = await get_donations_total(currency="RUB")
    percent = min(int(donated / SERVER_COST * 100), 100)
    filled = min(percent // 10, 10)
    bar = "█" * filled + "░" * (10 - filled)
    month = _next_month_name()

    if short:
        return (
            f"Сбор на сервер в {month}: {_money(donated)} из {_money(SERVER_COST)} ₽ ({percent}%).\n"
            f"{bar}\n"
            f"Поддержать проект можно в разделе «Донат»."
        )

    if percent >= 100:
        return (
            f"<b>Сбор на сервер в {month}</b>\n\n"
            f"{bar} <b>100%</b>\n\n"
            f"Собрано {_money(donated)} из {_money(SERVER_COST)} ₽. "
            f"Спасибо всем, кто помог."
        )

    return (
        f"<b>Сбор на сервер в {month}</b>\n\n"
        f"Собрано {_money(donated)} из {_money(SERVER_COST)} ₽ ({percent}%).\n"
        f"{bar}\n\n"
        f"Деньги идут только на аренду сервера. Поддержать можно в разделе «Донат»."
    )

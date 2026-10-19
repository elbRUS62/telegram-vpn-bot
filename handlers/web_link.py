"""Привязка веб-пользователя к Telegram-боту.

Когда B получил подписку через сайт (веб-выдача), он может зайти
в бота по ссылке t.me/skrepnet_bot?start=link_<token>.
Бот создаёт запись в users на основе invite_links и привязывает ссылку к TG.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message

from config import ADMIN_IDS, BOT_NAME
from database import (
    get_user,
    get_invite_link_any,
    bind_web_user_to_telegram,
)
from handlers.menu import show_main_menu

router = Router()
logger = logging.getLogger(__name__)


async def handle_web_link(message: Message, token: str):
    """Обработка /start link_<token>.

    Логика:
      1. Если B уже в users → ошибка
      2. Найти invite_link по токену → не найден → ошибка
      3. Если не активирован (is_used=0) → ошибка
      4. Если уже привязан к другому TG → ошибка
      5. Привязать (создать users + пометить invite_links.bound_to_tg_id)
      6. Уведомить A и админов
      7. Показать B главное меню
    """
    tg_id = message.from_user.id

    # 1. Проверить, что B ещё не в users
    existing = await get_user(tg_id)
    if existing:
        await message.answer(
            "⚠️ <b>У тебя уже есть подписка</b>\n\n"
            "Эту ссылку использовать нельзя — она одноразовая.\n\n"
            "Нажми «🔑 Моя подписка», чтобы посмотреть свои данные.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 2. Найти invite_link
    link = await get_invite_link_any(token)
    if not link:
        await message.answer(
            "❌ <b>Ссылка недействительна</b>\n\n"
            "Возможно, она была удалена или не существует.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 3. Проверить, что ссылка активирована на сайте
    if not link["is_used"]:
        await message.answer(
            "⏳ <b>Ссылка ещё не активирована</b>\n\n"
            "Сначала открой её в браузере и получи подписку на сайте, "
            "а потом возвращайся в бота.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 4. Проверить, что ссылка не привязана к другому TG
    if link["bound_to_tg_id"] is not None:
        await message.answer(
            "⚠️ <b>Ссылка уже привязана</b>\n\n"
            "Кто-то другой уже использовал её для входа в бота.\n"
            "Ссылка одноразовая.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 4.5. ЖЁСТКАЯ ПРОВЕРКА: если A указал friend_user_id — должен совпасть
    if link["friend_user_id"] is not None and link["friend_user_id"] != tg_id:
        logger.warning(
            f"⚠️ Попытка привязки по чужой ссылке: "
            f"token={token}, ожидается TG={link['friend_user_id']}, пришёл TG={tg_id}"
        )
        await message.answer(
            "⚠️ <b>Эта ссылка не для тебя</b>\n\n"
            "Она создана для другого пользователя.\n"
            "Попроси у пригласившего новую.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 5. Привязать (создаёт users + обновляет invite_links)
    bound_id = await bind_web_user_to_telegram(
        token=token,
        telegram_id=tg_id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or "",
    )

    if bound_id is None:
        # Гонка: между проверками кто-то успел привязать
        await message.answer(
            "⚠️ <b>Не удалось привязать</b>\n\n"
            "Ссылка уже кем-то использована. Попроси новую.",
            parse_mode="HTML"
        )
        await show_main_menu(message)
        return

    # 6. Уведомить A (пригласившего)
    inviter_id = link["created_by"]
    try:
        await message.bot.send_message(
            inviter_id,
            f"🎉 <b>Пользователь @{message.from_user.username or message.from_user.first_name} "
            f"активировал подписку по твоей ссылке!</b>\n\n"
            f"Спасибо, что помогаешь проекту расти ❤️",
            parse_mode="HTML",
            disable_notification=True,
        )
    except Exception as e:
        logger.warning("Не удалось уведомить пригласившего {inviter_id}: ")

    # 7. Уведомить админов
    admin_text = (
        f"🆕 <b>Веб-пользователь привязался к боту</b>\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 <code>{tg_id}</code>\n"
        f"📧 {link['xui_email']}\n"
        f"👥 Пригласил: <code>{inviter_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text,
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception as e:
            logger.error("Ошибка отправки админу {admin_id}: ")

    logger.info(f"✅ Веб-пользователь {tg_id} привязан к боту (token={token})")

    # 8. Показать B приветствие + главное меню
    await message.answer(
        f"🎉 <b>Добро пожаловать в {BOT_NAME}!</b>\n\n"
        f"Твоя подписка привязана к этому Telegram-аккаунту.\n"
        f"Теперь её можно продлевать через бота.",
        parse_mode="HTML"
    )
    await show_main_menu(message)

async def bind_by_tg_id(message: Message, link):
    """Автопривязка по TG ID (без токена).

    Вызывается из cmd_start, если найдена активная ссылка
    с friend_user_id = message.from_user.id.
    """
    tg_id = message.from_user.id

    # Проверить, что пользователя ещё нет в users
    existing = await get_user(tg_id)
    if existing:
        # Уже в users — просто меню
        logger.info(f"ℹ️ TG={tg_id} уже в users, автопривязка не нужна")
        await show_main_menu(message)
        return

    # Проверить ещё раз, что ссылка не привязана
    # (между поиском в start.py и этой функцией могла случиться гонка)
    bound_id = await bind_web_user_to_telegram(
        token=link["token"],
        telegram_id=tg_id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or "",
    )

    if bound_id is None:
        logger.warning(f"⚠️ Автопривязка не удалась: token={link['token']}, tg={tg_id}")
        await show_main_menu(message)
        return

    # Уведомить A (пригласившего)
    inviter_id = link["created_by"]
    try:
        await message.bot.send_message(
            inviter_id,
            f"🎉 <b>Пользователь @{message.from_user.username or message.from_user.first_name} "
            f"активировал подписку по твоей ссылке!</b>\n\n"
            f"Спасибо, что помогаешь проекту расти ❤️",
            parse_mode="HTML",
            disable_notification=True,
        )
    except Exception as e:
        logger.warning("Не удалось уведомить пригласившего {inviter_id}: ")

    # Уведомить админов
    admin_text = (
        f"🆕 <b>Веб-пользователь привязался к боту (авто)</b>\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 <code>{tg_id}</code>\n"
        f"📧 {link['xui_email']}\n"
        f"👥 Пригласил: <code>{inviter_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text,
                parse_mode="HTML",
                disable_notification=True
            )
        except Exception as e:
            logger.error("Ошибка отправки админу {admin_id}: ")

    logger.info(f"✅ Автопривязка: TG={tg_id} → token={link['token']}")

    # Приветствие + меню
    await message.answer(
        f"🎉 <b>Добро пожаловать в {BOT_NAME}!</b>\n\n"
        f"Твоя подписка привязана к этому Telegram-аккаунту.\n"
        f"Теперь её можно продлевать через бота.",
        parse_mode="HTML"
    )
    await show_main_menu(message)
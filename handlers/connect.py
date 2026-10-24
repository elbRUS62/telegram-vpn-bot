from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import BOT_NAME
from keyboards import connect_keyboard, back_to_connect_keyboard

router = Router()


@router.callback_query(F.data == "connect_help")
async def connect_help(callback: CallbackQuery):
    text = (
        f"<b>Как подключиться к {BOT_NAME}</b>\n\n"
        "Выбери своё устройство. Для каждого есть пошаговая инструкция."
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=connect_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        # Сообщение с фото (после QR) — удаляем и шлём новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text,
            reply_markup=connect_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "connect_android")
async def connect_android(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Android</b>\n\n"
        "<b>Приложение: Happ — Proxy Utility</b>\n"
        "1. Установи <b>Happ</b> из <a href='https://play.google.com/store/apps/details?id=com.happproxy'>Google Play</a>.\n"
        "2. Скопируй ссылку в разделе «Моя подписка».\n"
        "3. В Happ нажми «+» → «Добавить подписку».\n"
        "4. Вставь ссылку и сохрани профиль.\n"
        "5. Обнови подписку, если список серверов пуст.\n"
        "6. Выбери сервер и нажми «Подключиться».\n\n"
        "Разреши VPN в системном запросе. Если подключение не появилось, "
        "отключи экономию батареи для Happ.\n\n"
        "<i>Альтернативы:</i> Hysteria, v2rayNG.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "connect_ios")
async def connect_ios(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>iOS (iPhone / iPad)</b>\n\n"
        "<b>Приложение: Happ — Proxy Utility</b>\n"
        "1. Установи <b>Happ</b> из <a href='https://apps.apple.com/us/app/happ-proxy-utility/id6504287215'>App Store</a>.\n"
        "2. Скопируй ссылку в разделе «Моя подписка».\n"
        "3. В Happ нажми «+» → «Добавить подписку».\n"
        "4. Вставь ссылку и сохрани профиль.\n"
        "5. Обнови подписку, если список серверов пуст.\n"
        "6. Выбери сервер и включи VPN.\n\n"
        "Разреши добавление VPN-конфигурации в настройках iOS.\n\n"
        "<i>Если приложения нет в российском App Store, смени регион Apple ID на США.</i>\n"
        "<i>Альтернативы:</i> Streisand, Shadowrocket.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "connect_windows")
async def connect_windows(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Windows</b>\n\n"
        "<b>Приложение: Happ — Proxy Utility</b>\n"
        "1. Скачай <b>Happ</b> с <a href='https://www.happ.su/main/'>официального сайта</a>.\n"
        "2. Скопируй ссылку в разделе «Моя подписка».\n"
        "3. В Happ нажми «+» → «Добавить подписку».\n"
        "4. Вставь ссылку и сохрани профиль.\n"
        "5. Обнови подписку, если список серверов пуст.\n"
        "6. Выбери сервер и подключись.\n\n"
        "Если TUN не поднимается, запусти Happ от имени администратора.\n\n"
        "<i>Альтернатива:</i> Hysteria для Windows.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "connect_macos")
async def connect_macos(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>macOS</b>\n\n"
        "<b>Приложение: Happ — Proxy Utility</b>\n"
        "1. Установи <b>Happ</b> из <a href='https://apps.apple.com/us/app/happ-proxy-utility/id6504287215'>App Store</a>.\n"
        "2. Скопируй ссылку в разделе «Моя подписка».\n"
        "3. В Happ нажми «+» → «Добавить подписку».\n"
        "4. Вставь ссылку и сохрани профиль.\n"
        "5. Обнови подписку, если список серверов пуст.\n"
        "6. Выбери сервер и включи VPN.\n\n"
        "Разреши системное расширение VPN в настройках безопасности macOS.\n\n"
        "<i>Альтернативы:</i> Streisand, Clash Verge.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "connect_androidtv")
async def connect_androidtv(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Android TV</b>\n\n"
        "<b>Способ 1. Через телефон</b>\n"
        "1. Установи <b>Happ</b> на телефон и добавь подписку.\n"
        "2. Установи <b>v2rayTun</b> на телевизор из Google Play.\n"
        "3. Открой v2rayTun на телевизоре → «Импорт с телефона».\n"
        "4. Отсканируй QR-код.\n\n"
        "<b>Способ 2. Happ на телевизоре</b>\n"
        "1. Скачай APK <b>Happ</b> с <a href='https://www.happ.su/main/'>happ.su</a>.\n"
        "2. Установи через Send Files to TV или флешку.\n"
        "3. Разреши установку из неизвестных источников.\n"
        "4. Добавь подписку и выбери сервер.\n\n"
        "Если пульт неудобен, используй импорт по QR-коду.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "connect_linux")
async def connect_linux(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Linux</b>\n\n"
        "<b>Приложение: Happ — Proxy Utility</b>\n"
        "1. Скачай <b>Happ</b> для Linux с <a href='https://www.happ.su/main/'>happ.su</a>.\n"
        "2. Выбери сборку:\n"
        "   • <code>.deb</code> — Ubuntu / Debian\n"
        "   • <code>.rpm</code> — Fedora / CentOS\n"
        "   • <code>.AppImage</code> — универсальная\n"
        "3. Установи и запусти приложение.\n"
        "4. Скопируй ссылку в разделе «Моя подписка».\n"
        "5. В Happ нажми «+» → «Добавить подписку».\n"
        "6. Выбери сервер и подключись.\n\n"
        "Для TUN-режима может потребоваться запуск с повышенными правами.\n\n"
        "<i>Альтернативы:</i> Hysteria, Nekoray, Clash Verge.",
        reply_markup=back_to_connect_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

from docs_config import DOCS
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    KeyboardButtonRequestUsers,
    WebAppInfo
)
from config import DONATE_URL, BOT_NAME, SUPPORT_USERNAME, MINIAPP_URL


# ============================================================
# ГЛАВНОЕ МЕНЮ (ReplyKeyboard — только «Поддержать проект»)
# ============================================================

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❤️ Поддержать проект")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def admin_menu():
    return main_menu()


def main_inline_menu(is_admin: bool = False):
    """Главное inline-меню. «Прогресс сбора» — только админу."""
    rows = [
        [
            InlineKeyboardButton(text="📦 Получить подписку", callback_data="menu_get_sub"),
            InlineKeyboardButton(text="🔑 Моя подписка", callback_data="menu_my_sub"),
        ],
        [
            InlineKeyboardButton(text="👥 Пригласить пользователя", callback_data="menu_invite"),
            InlineKeyboardButton(text="➕ Добавить без TG", callback_data="menu_invite_no_tg"),
        ],
        [
            InlineKeyboardButton(
    text="🆘 Техподдержка",
    url=f"https://t.me/{SUPPORT_USERNAME}"
),
            InlineKeyboardButton(text="📚 Документы", callback_data="menu_docs"),
        ],
    ]

    if is_admin:
        rows.append([
            InlineKeyboardButton(text="📊 Прогресс сбора", callback_data="menu_progress"),
        ])
        rows.append([
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="🛠 Управление", callback_data="admin_manage"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# ОСТАЛЬНЫЕ КЛАВИАТУРЫ (без изменений, только добавил «Назад»)
# ============================================================

def admin_manage_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список заявок", callback_data="admin_list_requests"),
            InlineKeyboardButton(text="🔄 Обновить подписку", callback_data="admin_extend"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_menu_users"),
        ],
        [
            InlineKeyboardButton(text="🔐 Панель 3x-ui", callback_data="admin_panel"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"),
        ],
    ])


def admin_submenu_users():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♻️ Сбросить заявку", callback_data="admin_reset")],
        [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data="admin_delete_user")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage")],
    ])


def admin_approve_keyboard(telegram_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{telegram_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{telegram_id}")
        ]
    ])


def donate_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Поддержать звёздами", callback_data="donate_stars")],
        [InlineKeyboardButton(text="💸 DonationAlerts", url=DONATE_URL)],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
    ])


def donate_stars_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 10 звёзд", callback_data="stars_10")],
        [InlineKeyboardButton(text="⭐ 25 звёзд", callback_data="stars_25")],
        [InlineKeyboardButton(text="⭐ 50 звёзд", callback_data="stars_50")],
        [InlineKeyboardButton(text="⭐ 100 звёзд", callback_data="stars_100")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_donate")]
    ])


def renew_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="renew")],
        [InlineKeyboardButton(text="❤️ Поддержать проект", url=DONATE_URL)],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
    ])


def subscription_keyboard():
    from config import MINIAPP_URL

    rows = []

    if MINIAPP_URL:
        rows.append([InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(url=MINIAPP_URL)
        )])

    rows += [
        [InlineKeyboardButton(text="📖 Как подключиться", callback_data="connect_help")],
        [InlineKeyboardButton(text="📷 QR-код", callback_data="show_qr")],
        [InlineKeyboardButton(text="🔄 Продлить", callback_data="renew")],
        [InlineKeyboardButton(text="❤️ Поддержать", url=DONATE_URL)],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def share_keyboard(bot_username: str, telegram_id: int):
    share_text = f"Присоединяйся к {BOT_NAME} — бесплатный VPN!"
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{telegram_id}&text={share_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться с друзьями", url=share_url)],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
    ])


def connect_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Android", callback_data="connect_android")],
        [InlineKeyboardButton(text="🍎 iOS", callback_data="connect_ios")],
        [InlineKeyboardButton(text="💻 Windows", callback_data="connect_windows")],
        [InlineKeyboardButton(text="🖥 macOS", callback_data="connect_macos")],
        [InlineKeyboardButton(text="📺 Android TV", callback_data="connect_androidtv")],
        [InlineKeyboardButton(text="🐧 Linux", callback_data="connect_linux")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
    ])


def back_to_connect_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="connect_help")]
    ])


def terms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=DOCS["rules"]["title"], url=DOCS["rules"]["url"])],
        [InlineKeyboardButton(text=DOCS["privacy"]["title"], url=DOCS["privacy"]["url"])],
        [InlineKeyboardButton(text=DOCS["terms"]["title"], url=DOCS["terms"]["url"])],
        [InlineKeyboardButton(text="✅ Я согласен со всеми условиями", callback_data="accept_terms")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="decline_terms")]
    ])


def admin_panel_keyboard():
    panel_url = "https://ru-skrepnet.duckdns.org:3775/MASbquuCRx18QVK8l6/panel"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Войти в 3x-ui", url=panel_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage")],
    ])


def support_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Техподдержка", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
    ])


def documents_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=DOCS["rules"]["title"], url=DOCS["rules"]["url"])],
        [InlineKeyboardButton(text=DOCS["privacy"]["title"], url=DOCS["privacy"]["url"])],
        [InlineKeyboardButton(text=DOCS["terms"]["title"], url=DOCS["terms"]["url"])],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ])


def back_to_documents_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ])


def invite_no_tg_inline_keyboard():
    """Inline-версия меню «Добавить без Telegram»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✍️ Ввести @username или ID",
            callback_data="invite_manual_start"
        )],
        [InlineKeyboardButton(
            text="⬅️ В главное меню",
            callback_data="back_to_main"
        )],
    ])


def invite_share_keyboard(invite_url: str):
    share_text = f"Присоединяйся к {BOT_NAME} — бесплатный VPN!"
    share_url = f"https://t.me/share/url?url={invite_url}&text={share_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=share_url)],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main")],
    ])


def email_conflict_keyboard(telegram_id: int, base_email: str):
    suggested = [f"{base_email}_2", f"{base_email}_3", f"{base_email}_4"]
    id_email = f"{base_email}_{telegram_id}"

    buttons = []
    buttons.append([InlineKeyboardButton(
        text=f"♻️ Использовать существующий {base_email}",
        callback_data=f"use_existing:{telegram_id}"
    )])
    for email in suggested:
        buttons.append([InlineKeyboardButton(
            text=f"📧 {email}",
            callback_data=f"retry_email:{telegram_id}:{email}"
        )])
    buttons.append([InlineKeyboardButton(
        text=f"🆔 {id_email}",
        callback_data=f"retry_email:{telegram_id}:{id_email}"
    )])
    buttons.append([InlineKeyboardButton(
        text="✍️ Ввести вручную",
        callback_data=f"manual_email:{telegram_id}"
    )])
    buttons.append([InlineKeyboardButton(
        text="❌ Отменить заявку",
        callback_data=f"cancel_email:{telegram_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def users_list_keyboard(users: list, action: str, page: int, total: int, per_page: int = 10):
    buttons = []

    for user in users:
        if user["username"]:
            display = f"@{user['username']}"
            if user["first_name"]:
                display += f" — {user['first_name']}"
        elif user["first_name"]:
            display = f"{user['first_name']} — {user['telegram_id']}"
        else:
            display = str(user["telegram_id"])

        if len(display) > 60:
            display = display[:60] + "…"

        buttons.append([InlineKeyboardButton(
            text=display,
            callback_data=f"user_action:{action}:{user['telegram_id']}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"users_page:{action}:{page - 1}"
        ))

    total_pages = (total + per_page - 1) // per_page
    nav.append(InlineKeyboardButton(
        text=f"{page + 1}/{total_pages}",
        callback_data="noop"
    ))

    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"users_page:{action}:{page + 1}"
        ))

    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="admin_manage"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def waitlist_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📝 Встать в лист ожидания",
            callback_data="join_waitlist"
        )],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
    ])


def invite_contact_keyboard():
    """ReplyKeyboard ТОЛЬКО для сценария 'Добавить без TG'."""
    from aiogram.types import KeyboardButtonRequestUsers

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="👤 Выбрать из контактов",
                request_users=KeyboardButtonRequestUsers(
                    request_id=1,
                    user_is_bot=False,
                    max_quantity=1,
                    request_name=True,
                    request_username=True,
                )
            )],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
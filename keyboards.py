from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .config import REVIEWS_URL, SITE_URL, APPSTORE_URL, GOOGLEPLAY_URL, WINDOWS_GUIDE_URL, MAC_GUIDE_URL, TV_GUIDE_URL, FAQ_URL, SUPPORT_USERNAME, PARTNER_INFO_URL

# === Главное меню (каждая кнопка - СВОЯ строка) ===
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключить VPN", callback_data="connect")],
        [InlineKeyboardButton(text="💳 Продлить", callback_data="renew")],
        [InlineKeyboardButton(text="🎁 Пригласить", callback_data="invite")],
        [InlineKeyboardButton(text="⚡ VPNpower", callback_data="about")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")],
    ])

# === Подключить → выбор устройства (сеткой 3 + 2) ===
def kb_devices() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍏 iOS",       callback_data="dev_ios")],
        [InlineKeyboardButton(text="🤖 Android",   callback_data="dev_android")],
        [InlineKeyboardButton(text="🪟 Windows",   callback_data="dev_windows")],
        [InlineKeyboardButton(text="💻 Mac",       callback_data="dev_mac")],
        [InlineKeyboardButton(text="📺 Телевизор", callback_data="dev_tv")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

# === Кнопки с инструкциями для платформ + Подключить ===
def kb_device_detail(platform: str, has_store_link: bool = True) -> InlineKeyboardMarkup:
    rows = []

    if platform == "ios":
        if has_store_link:
            rows.append([InlineKeyboardButton(text="🍏 Скачать в App Store", url=APPSTORE_URL)])
        rows.append([InlineKeyboardButton(text="⚙️ Подключить 🍏", callback_data="go_ios")])
        rows.append([InlineKeyboardButton(text="📘 Инструкция iPhone/iPad", url=APPSTORE_URL)])
    elif platform == "android":
        if has_store_link:
            rows.append([InlineKeyboardButton(text="🤖 Скачать в Google Play", url=GOOGLEPLAY_URL)])
        rows.append([InlineKeyboardButton(text="⚙️ Подключить 🤖", callback_data="go_android")])
        rows.append([InlineKeyboardButton(text="📘 Инструкция Android", url=GOOGLEPLAY_URL)])
    elif platform == "windows":
        rows.append([InlineKeyboardButton(text="📘 Инструкция Windows", url=WINDOWS_GUIDE_URL)])
        rows.append([InlineKeyboardButton(text="⚙️ Подключить 🪟", callback_data="go_windows")])
    elif platform == "mac":
        rows.append([InlineKeyboardButton(text="📘 Инструкция MacBook", url=MAC_GUIDE_URL)])
        rows.append([InlineKeyboardButton(text="⚙️ Подключить 💻", callback_data="go_mac")])
    elif platform == "tv":
        rows.append([InlineKeyboardButton(text="📘 Инструкция TV", url=TV_GUIDE_URL)])
        rows.append([InlineKeyboardButton(text="⚙️ Подключить 📺", callback_data="go_tv")])

    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# === О сервисе: ДВЕ кнопки в ОДНОЙ строке ===
def kb_about() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_URL),
         InlineKeyboardButton(text="🌐 Наш сайт", url=SITE_URL)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

# === Помощь ===
def kb_help() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="📖 FAQ", url=FAQ_URL)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

# === Пригласить ===
def kb_invite() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ О партнерской программе", url=PARTNER_INFO_URL)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

# === Тарифы (оставляем выбор в дальнейшем; пока только верстка) ===
def kb_tariffs() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Мощь", callback_data="tarif_power")],
        [InlineKeyboardButton(text="🚀 Абсолютная Мощь", callback_data="tarif_absolute")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

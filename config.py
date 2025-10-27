# bot/config.py
from __future__ import annotations

import os
from pathlib import Path

# --- dotenv может отсутствовать; делаем безопасный импорт ---
try:
    from dotenv import load_dotenv
except Exception:  # библиотека не установлена — работаем без неё
    def load_dotenv(*args, **kwargs):
        return False

# === Путь к корню проекта и .env ===
ROOT_DIR = Path(__file__).resolve().parents[1]     # <repo root>
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)  # загружаем .env из корня


def _get(name: str, default: str = "") -> str:
    """Берём переменную окружения и аккуратно обрезаем пробелы."""
    return os.getenv(name, default).strip()


# === Brand ===
BRAND_NAME = _get("BRAND_NAME", "VPNpower")


# === Bot / API ===
BOT_TOKEN = _get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")

# Поддерживаем как BACKEND_URL, так и устаревший API_BASE_URL
BACKEND_URL = _get("BACKEND_URL") or _get("API_BASE_URL", "http://127.0.0.1:8000")
BACKEND_URL = BACKEND_URL.rstrip("/")

# === Subscriptions backend (compat with /vless) ===
SUB_BASE_URL = _get("SUB_BASE_URL") or BACKEND_URL
SUB_BASE_URL = SUB_BASE_URL.rstrip("/")
JWT_SECRET   = _get("JWT_SECRET", "")
TG_LINK_SECRET = _get("TG_LINK_SECRET", "")



# === Links ===
REVIEWS_URL = _get("REVIEWS_URL", "https://t.me/VPNpowerfeedback")
SITE_URL    = _get("SITE_URL",    "https://vpnpower.ru")

# AppStore / Google Play — оставляем алиасы для совместимости
APPSTORE_URL    = _get("APPSTORE_URL") or _get("IOS_APP_URL", "https://apps.apple.com")
IOS_APP_URL     = APPSTORE_URL  # alias для старого кода

GOOGLEPLAY_URL  = _get("GOOGLEPLAY_URL") or _get("ANDROID_APP_URL", "https://play.google.com")
ANDROID_APP_URL = GOOGLEPLAY_URL  # alias для старого кода

WINDOWS_GUIDE_URL = _get("WINDOWS_GUIDE_URL", "https://telegra.ph/Windows-Guide-01-01")
MAC_GUIDE_URL     = _get("MAC_GUIDE_URL",     "https://telegra.ph/MacOS-Guide-01-01")
TV_GUIDE_URL      = _get("TV_GUIDE_URL",      "https://telegra.ph/AndroidTV-Guide-01-01")
FAQ_URL           = _get("FAQ_URL",           "https://vpnpower.ru/faq")
PARTNER_INFO_URL  = _get("PARTNER_INFO_URL",  "https://vpnpower.ru/partners")


# === Support ===
# Поддерживаем оба варианта .env:
#   SUPPORT_USERNAME=YourSupport (без @)
#   ИЛИ SUPPORT_HANDLE=@YourSupport
_support_username = _get("SUPPORT_USERNAME")
if not _support_username:
    _support_username = _get("SUPPORT_HANDLE")  # может прийти с @
SUPPORT_USERNAME = _support_username.lstrip("@") or "Support"
SUPPORT_HANDLE   = f"@{SUPPORT_USERNAME}"  # alias для старого кода


# === Media (баннер) ===
# Если есть рабочий file_id — используем его; иначе локальный файл.
_raw_file_id = _get("BANNER_FILE_ID")
BANNER_FILE_ID   = _raw_file_id if _raw_file_id else None

BANNER_FILE_PATH = _get("BANNER_FILE_PATH", "bot/assets/vpn.mp4")
# Абсолютный путь — удобно для FSInputFile и надёжно при разных точках запуска
BANNER_ABS_PATH  = (ROOT_DIR / BANNER_FILE_PATH).resolve()
# Используем абсолютный путь по умолчанию
BANNER_FILE_PATH = str(BANNER_ABS_PATH)


# === Таймауты / прочее ===
def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default

REQUEST_TIMEOUT = _get_float("REQUEST_TIMEOUT", 15.0)


# === Диагностика (по желанию) ===
def dump_config_for_logs() -> dict:
    """Короткий дамп для логов/отладки (без секретов)."""
    return {
        "BRAND_NAME": BRAND_NAME,
        "BACKEND_URL": BACKEND_URL,
        "REVIEWS_URL": REVIEWS_URL,
        "SITE_URL": SITE_URL,
        "APPSTORE_URL": APPSTORE_URL,
        "GOOGLEPLAY_URL": GOOGLEPLAY_URL,
        "SUPPORT_HANDLE": SUPPORT_HANDLE,
        "BANNER_FILE_ID_set": bool(BANNER_FILE_ID),
        "BANNER_FILE_PATH": str(BANNER_ABS_PATH),
        "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
    }

PUBLIC_URL = "https://vpnpower.ru"

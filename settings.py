# backend/settings.py
import os
from typing import Optional
from urllib.parse import urlencode
from dotenv import load_dotenv, find_dotenv

# Загружаем .env (локально и на стенде)
load_dotenv(find_dotenv(), override=True)

def _get_env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default

def _normalize_base_url(url: str) -> str:
    return (url or "").rstrip("/")

class Settings:
    BRAND_NAME: str = os.getenv("BRAND_NAME", "VPNpower")
    API_SECRET: str = os.getenv("API_SECRET", "change-this-api-secret")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change_this_jwt_secret")
    TG_LINK_SECRET: str | None = os.getenv("TG_LINK_SECRET")

    # Только Neon / PostgreSQL
    DATABASE_URL: str = os.getenv("DATABASE_URL") or ""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL env var is required (Neon PostgreSQL)")

    DEFAULT_FLOW: str = os.getenv("DEFAULT_FLOW", "xtls-rprx-vision")
    DEFAULT_FP: str = os.getenv("DEFAULT_FP", "chrome")

    TRIAL_DAYS: int = _get_env_int("TRIAL_DAYS", 3)
    SUB_MAX_DEVICES: int = _get_env_int("SUB_MAX_DEVICES", 5)

    # Обычно уже с /sub в пути
    SUB_BASE_URL: str = _normalize_base_url(os.getenv("SUB_BASE_URL", "http://127.0.0.1:8000/sub"))

    SUB_MODE_DEFAULT: str = os.getenv("SUB_MODE_DEFAULT", "auto").strip().lower()
    if SUB_MODE_DEFAULT not in ("auto", "list"):
        SUB_MODE_DEFAULT = "auto"

    AUTO_LIST_THRESHOLD: int = _get_env_int("AUTO_LIST_THRESHOLD", 3)
    SUB_AUTO_TOP_N: int = _get_env_int("SUB_AUTO_TOP_N", 1)

    def build_subscription_link(
        self,
        token: str,
        *,
        platform: Optional[str] = None,
        device_token: Optional[str] = None,
        region: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> str:
        base = f"{self.SUB_BASE_URL}/{token}"
        params = {}
        if platform:
            params["p"] = platform
        if device_token:
            params["d"] = device_token
        if region:
            params["r"] = region
        if mode and mode in ("auto", "list"):
            params["mode"] = mode
        return base if not params else f"{base}?{urlencode(params)}"

settings = Settings()

# bot/deeplink.py
from __future__ import annotations

import json
from urllib.parse import urlencode, quote
from urllib.request import urlopen, Request

# --- Конфиг/URL-ы ---
try:
    from .config import BACKEND_URL  # http://127.0.0.1:8000
except Exception:
    BACKEND_URL = "http://127.0.0.1:8000"

# Публичная база для ссылок (домен сайта)
_PUBLIC = None
try:
    from .config import PUBLIC_URL as _PUBLIC  # приоритетно
except Exception:
    try:
        from .config import PUBLIC_HOST as _PUBLIC  # если вдруг так названо
    except Exception:
        _PUBLIC = None
HOST = (_PUBLIC or "https://vpnpower.ru").rstrip("/")

def _http_json(url: str, *, method: str = "GET", params: dict | None = None) -> dict:
    # Бэкенд ожидает параметры в query даже для POST (совместимость)
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    req = Request(url, method=method)
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def _oneclick_link(tg_id: int, platform: str = "ios") -> str:
    return _http_json(
        f"{BACKEND_URL}/oneclick", method="GET",
        params={"tg_id": str(tg_id), "platform": platform}
    )["link"]

def _create_alias(key: str, tg_id: int) -> str:
    # key: full URL (/sub/...), token=..., raw JWT — всё поддерживается на бэкенде
    data = _http_json(
        f"{BACKEND_URL}/api/alias/create",
        method="POST",
        params={"token": key, "user_id": str(tg_id)}
    )
    return data["alias"]

# ===== ПУБЛИЧНЫЕ API, которые дергает bot.py =====

def build_subscription_url(*args, **kwargs) -> str:
    """
    Совместимая оболочка.
    Новый способ: build_subscription_url(tg_id=...)
      -> вернёт URL подписки https://<host>/s/<alias>
    Старый способ: build_subscription_url(<уже_готовый_sub_url>, ...)
      -> вернёт то, что передали (не ломаем старые вызовы).
    """
    tg_id = kwargs.get("tg_id")
    if tg_id is None and args and isinstance(args[0], int):
        tg_id = args[0]

    if tg_id is None:
        # старый путь: первый аргумент — уже готовый sub_url
        return args[0] if args else ""

    key = _oneclick_link(tg_id, kwargs.get("platform", "ios"))
    alias = _create_alias(key, tg_id)
    return f"{HOST}/s/{alias}"

def build_import_link(platform: str | None,
                      sub_or_url: str,
                      name: str = "VPNpower",
                      redirect: bool = True,
                      **kwargs) -> str:
    """
    Если передан tg_id -> строим короткий диплинк /dl/<platform>/<alias>.
    Иначе (обратная совместимость) -> /dl/sub?url=<...>&platform=<...>[&redirect=1]
    """
    plat = (platform or "").lower()
    tg_id = kwargs.get("tg_id")

    if tg_id is not None and plat:
        # alias-поток
        key = _oneclick_link(tg_id, platform="ios")  # токен универсальный
        alias = _create_alias(key, tg_id)
        if   plat == "windows": plat = "win"
        elif plat not in ("ios", "android", "mac", "win"):  # на всякий
            plat = "ios"
        return f"{HOST}/dl/{plat}/{alias}"

    # старый поток — без tg_id
    if plat in ("ios", "android"):
        base = f"{HOST}/dl/sub?url={quote(sub_or_url, safe='')}&platform={plat}"
        if redirect:
            base += "&redirect=1"
        return base
    return sub_or_url


def get_text(url: str, timeout: int = 8) -> str:
    "Скачивает и возвращает text/plain (для /s/<alias> или /sub/vless?token=...)"
    try:
        with urlopen(url, timeout=timeout) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ""

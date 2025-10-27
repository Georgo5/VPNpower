# backend/routers/deeplink_platform.py
from __future__ import annotations

import os
import secrets
import urllib.parse as up

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["deeplink"])


def _host_base(req: Request) -> str:
    host = (
        req.headers.get("x-forwarded-host")
        or req.headers.get("host")
        or (req.url.hostname or "vpnpower.ru")
    )
    scheme = req.headers.get("x-forwarded-proto") or req.url.scheme or "https"
    return f"{scheme}://{host}"


@router.get("/connect", response_class=HTMLResponse)
def connect(url: str | None = None, sub: str | None = None, name: str | None = None, auto: int = 1):
    brand = name or os.environ.get("BRAND_NAME", "VPNpower")
    if not url:
        return HTMLResponse(f"""<!doctype html><meta charset="utf-8">
<title>{brand} — Connect</title>
<h1>{brand}</h1>
<p>Параметр <code>url</code> не передан.</p>
""")
    # Минимальная HTML-страница с мгновенным переходом
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8">
<title>{brand} — Connect</title>
<meta http-equiv="refresh" content="0;url={url}">
<p>Если не открылось автоматически, нажмите:
  <a href="{url}">Открыть в приложении</a></p>
{f'<p>URL подписки: <a href="{sub}">{sub}</a></p>' if sub else ''}
""")


@router.get("/dl/sub")
def dl_sub(url: str):
    """Редиректит на /connect?url=... (подписка уже сформирована внешним кодом)"""
    return RedirectResponse(url=f"/connect?url={up.quote(url, safe='')}", status_code=307)


@router.get("/dl/ios/{key}")
def dl_ios(key: str, request: Request):
    """
    Собирает ссылку вида:
      /connect/?url=v2raytun://import/https%3A%2F%2F<host>%2Fs%2F<key>%3Fd%3D<hex>&sub=https://<host>/s/<key>?d=<hex>&name=<BRAND>&auto=1
    """
    brand = os.environ.get("BRAND_NAME", "VPNpower")
    base = _host_base(request)
    d = secrets.token_hex(8)  # просто стабилизированный "salt" в query
    sub_url = f"{base}/s/{key}?d={d}"
    v2ray_import = f"v2raytun://import/{up.quote(sub_url, safe='')}"
    location = (
        f"/connect/?url={up.quote(v2ray_import, safe='')}"
        f"&sub={up.quote(sub_url, safe='')}"
        f"&name={up.quote(brand)}&auto=1"
    )
    return RedirectResponse(url=location, status_code=307)

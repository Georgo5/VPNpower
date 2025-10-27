from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from urllib.parse import quote

router = APIRouter()

PAGE = """<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VPNpower — Подключение</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:24px;line-height:1.45;background:#0b0f13;color:#e8eef3}
  .card{max-width:720px;margin:auto;background:#121820;border:1px solid #243040;border-radius:12px;padding:24px}
  h1{font-size:20px;margin:0 0 12px}
  p{margin:8px 0 12px;color:#bfd2e2}
  a.btn{display:inline-block;text-decoration:none;padding:12px 20px;border-radius:10px;border:1px solid #3b82f6}
  a.btn{background:#1a2330;color:#e8eef3}
  code{background:#1a2330;padding:2px 6px;border-radius:6px}
  .muted{color:#93a7bb}
</style>
<div class="card">
  <h1>Открыть в клиенте</h1>
  <p>Если приложение не открылось автоматически, нажмите кнопку:</p>
  <p><a class="btn" href="{IMPORT_URL}">Открыть VPN</a></p>
  <hr style="border-color:#243040">
  <p class="muted">Если кнопка не работает, скопируйте ссылку подписки и добавьте её вручную:</p>
  <p><code>{SUB_URL}</code></p>
</div>
</html>
"""

@router.get("/connect", response_class=HTMLResponse, include_in_schema=False)
async def connect_view(
    request: Request,
    url: str | None = Query(default=None, description="Готовый deeplink (v2raytun://import/...)"),
    sub: str | None = Query(default=None, description="Прямая ссылка на подписку https://.../s/<alias>"),
    name: str | None = Query(default="VPNpower"),
):
    # Если deeplink не передан, но есть подписка — соберём его сами
    if not url and sub:
        url = f"v2raytun://import/{quote(sub, safe=':/?&=')}"
    if not url:
        return HTMLResponse(PAGE.format(IMPORT_URL="#", SUB_URL=sub or ""), status_code=200)
    return HTMLResponse(PAGE.format(IMPORT_URL=url, SUB_URL=sub or ""), status_code=200)

# Легаси-страница: /dl/sub?url=... — оставляем на случай старых ссылок
@router.get("/dl/sub", response_class=HTMLResponse, include_in_schema=False)
async def legacy_sub_page(
    request: Request,
    url: str = Query(..., description="Прямая ссылка на подписку https://.../s/<alias>"),
):
    deeplink = f"v2raytun://import/{quote(url, safe=':/?&=')}"
    return HTMLResponse(PAGE.format(IMPORT_URL=deeplink, SUB_URL=url), status_code=200)

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["misc"])

@router.get("/redirect", response_class=HTMLResponse, summary="Открыть custom-scheme с запасным путём")
def open_redirect(app_url: str, fallback: str = "https://t.me/vpnpower_bot"):
    return f"""
    <!doctype html>
    <html><head><meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={app_url}">
    <title>VPNpower</title></head>
    <body>
      <p>Перенаправляю… Если ничего не произошло, <a href="{app_url}">нажмите здесь</a> или <a href="{fallback}">вернитесь в бот</a>.</p>
    </body></html>
    """

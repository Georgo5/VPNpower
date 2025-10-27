from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, PlainTextResponse
from urllib.parse import quote, urlparse

from .db import Base, engine

# Routers
from .routers import users as users_router
from .routers import subscription as subscription_router
from .routers import misc as misc_router
from .routers import oneclick
from .routers import me as me_router
from .routers import shortlink as shortlink_router
from .routers import deeplink_platform as deeplink_platform_router
from .routers import node_sync as node_sync_router  # <-- подключаем новый роутер
from backend.routers.tg_link import router as tg_link_router # <-- сбор тг айди

app = FastAPI(title="VPNpower API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры (без префикса, кроме /api для me)
app.include_router(users_router.router, prefix="")
app.include_router(subscription_router.router, prefix="")
app.include_router(misc_router.router, prefix="")
app.include_router(oneclick.router, prefix="")
app.include_router(me_router.router, prefix="/api")
app.include_router(shortlink_router.router, prefix="")
app.include_router(deeplink_platform_router.router, prefix="")
app.include_router(node_sync_router.router, prefix="")  # <-- так /api/nodes/active-uuids останется корректным
app.include_router(tg_link_router, prefix="/tg", tags=["telegram"]) # <-- сбор тг айди

@app.on_event("startup")
def on_startup():
    # создаём таблицы один раз (не мешает существующим)
    Base.metadata.create_all(bind=engine)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# ---- Deep-link builder для открытия подписки в V2RayTun ----
# Пример:
#   /dl/sub?url=http(s)%3A%2F%2Fhost%2Fsub%2Fvless%3Ftoken%3D...&name=VPNpower&style=install&redirect=true
@app.get("/dl/sub", summary="Deep link для открытия подписки в V2RayTun")
def dl_sub(
    url: str,
    platform: str = Query("ios", pattern="^(ios|android)$"),
    name: str | None = Query(None, description="Имя профиля (#Name)"),
    style: str = Query("install", pattern="^(install|import)$", description="Способ для V2RayTun"),
    redirect: bool = Query(True, description="Сразу сделать редирект в приложение"),
):
    sub_url = url.strip()
    if name and not urlparse(sub_url).fragment:
        sub_url = f"{sub_url}#{name}"

    if style == "import":
        deep = f"v2raytun://import/{sub_url}"
    else:
        deep = f"v2raytun://install-config?url={quote(sub_url, safe='')}"

    if redirect:
        return RedirectResponse(deep)
    return PlainTextResponse(deep)

# ---- Совместимый редирект (как у конкурента) ----
@app.get("/redirect", summary="Совместимый редирект в клиент (как у конкурента)")
def redirect_compat(
    url: str,
    platform: str = Query("ios", pattern="^(ios|android)$"),
    redirect: bool = Query(True, description="Сразу редиректить"),
):
    u = url.strip()
    if u.lower().startswith(("v2raytun://", "sing-box://", "shadowrocket://")):
        target = u
    else:
        target = f"v2raytun://install-config?url={quote(u, safe='')}"
    if redirect:
        return RedirectResponse(target)
    return PlainTextResponse(target)

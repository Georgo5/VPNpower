# backend/routers/tg_link.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from backend.settings import settings

router = APIRouter(tags=["telegram"])

# Пул подключений (неблокирующий; pre_ping, future API)
engine = create_engine(settings.DATABASE_URL, future=True, pool_pre_ping=True)


class LinkPayload(BaseModel):
    """
    Принимаем оба варианта имени:
      - telegram_username  (бот сейчас так шлёт)
      - tg_username        (встречалось в ранних версиях)
    """
    telegram_id: int
    telegram_username: Optional[str] = None
    tg_username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@router.post("/link", summary="Link User (telegram → users)", status_code=204)
def link_user(
    body: LinkPayload,
    # ОБЯЗАТЕЛЬНО: заголовок с дефисами, как принято в HTTP
    x_tg_link_secret: str = Header(..., alias="X-TG-Link-Secret"),
) -> Response:
    # 1) Авторизация по секрету
    if x_tg_link_secret != settings.TG_LINK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    # 2) Нормализация имени
    username = (body.telegram_username or body.tg_username or "").strip() or None
    full_name = " ".join(p for p in [(body.first_name or "").strip() or None,
                                     (body.last_name or "").strip() or None]
                         if p) or None

    # 3) Upsert по tg_id
    sql = text(
        """
        INSERT INTO public.users (tg_id, tg_username, first_name, last_name, full_name, updated_at)
        VALUES (:tg_id, :tg_username, :first_name, :last_name, :full_name, now())
        ON CONFLICT (tg_id) DO UPDATE SET
            tg_username = EXCLUDED.tg_username,
            first_name  = EXCLUDED.first_name,
            last_name   = EXCLUDED.last_name,
            full_name   = EXCLUDED.full_name,
            updated_at  = now()
        """
    )
    params = {
        "tg_id": body.telegram_id,
        "tg_username": username,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "full_name": full_name,
    }
    with engine.begin() as conn:
        conn.execute(sql, params)

    # 204 No Content
    return Response(status_code=204)

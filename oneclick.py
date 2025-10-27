# backend/routers/oneclick.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security_jwt import make_subscription_token
from ..settings import settings  # ожидаем settings.TRIAL_DAYS

router = APIRouter(tags=["oneclick"])

# Подстраховка: если в settings нет TRIAL_DAYS — используем 3
TRIAL_DAYS: int = getattr(settings, "TRIAL_DAYS", 3)


class OneClickRequest(BaseModel):
    telegram_id: int
    platform: Optional[str] = "ios"
    region: Optional[str] = None


class OneClickResponse(BaseModel):
    link: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_sub_url(request: Request, token: str) -> str:
    """
    Строим абсолютную ссылку на plaintext-подписку (VLESS URI-ы в теле ответа).
    Пример: http://127.0.0.1:8000/sub/vless?token=...
    """
    base = str(request.base_url).rstrip("/")
    return f"{base}/sub/vless?token={token}"


def _ensure_user(db: Session, telegram_id: int) -> User:
    """
    Гарантируем, что пользователь существует и имеет нужные значения:
      1) создаём при первом заходе;
      2) обеспечиваем legacy vless_uuid;
      3) при первом заходе запускаем бесплатный триал на TRIAL_DAYS;
      4) страхуем поля, если вдруг в БД отсутствуют дефолты.
    """
    user = db.query(User).filter(User.tg_id == telegram_id).first()

    if not user:
        # Новый пользователь
        user = User(tg_id=telegram_id)

        # UUID для совместимости со старым форматом ссылок
        user.ensure_uuid()

        # Авто‑триал на первые TRIAL_DAYS (если не нужно — закомментируй 2 строки ниже)
        user.subscription_active = True
        user.subscription_end_at = _now_utc() + timedelta(days=TRIAL_DAYS)

        # Подстраховка обязательных полей (если нет server default'ов)
        if getattr(user, "token_version", None) is None:
            user.token_version = 0

        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # Существующий пользователь — аккуратно дополним недостающее
    changed = False

    if not user.vless_uuid:
        user.ensure_uuid()
        changed = True

    # Если пользователь без активной подписки и вообще без срока — запустим триал
    if not user.subscription_active and not user.subscription_end_at:
        user.subscription_active = True
        user.subscription_end_at = _now_utc() + timedelta(days=TRIAL_DAYS)
        changed = True

    if getattr(user, "token_version", None) is None:
        user.token_version = 0
        changed = True

    if changed:
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


def _issue_link(
    db: Session,
    telegram_id: int,
    platform: Optional[str],
    region: Optional[str],
    request: Request,
) -> str:
    """
    Возвращаем URL на /sub/vless с JWT-токеном подписки (TTL токена ≈ 30 дней).
    Параметры platform/region пока «на будущее» — просто прокидываются.
    """
    user = _ensure_user(db, telegram_id)
    token = make_subscription_token(
        user_id=user.id,
        token_version=user.token_version,
        ttl_hours=24 * 30,  # срок действия ссылки (не путать со сроком подписки!)
    )
    return _build_sub_url(request, token)


# === POST /api/oneclick — основной API-метод ===
@router.post("/api/oneclick", response_model=OneClickResponse)
def oneclick_post(
    payload: OneClickRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> OneClickResponse:
    link = _issue_link(db, payload.telegram_id, payload.platform, payload.region, request)
    return OneClickResponse(link=link)


# === GET /oneclick — совместимость с ботом (tg_id | telegram_id) ===
@router.get("/oneclick", response_model=OneClickResponse)
def oneclick_get(
    request: Request,
    telegram_id: Optional[int] = Query(None, description="Telegram user id"),
    tg_id: Optional[int] = Query(None, description="Alias for telegram_id"),
    platform: Optional[str] = Query("ios"),
    region: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> OneClickResponse:
    user_tid = telegram_id or tg_id
    if not user_tid:
        raise HTTPException(status_code=422, detail="Provide tg_id (or telegram_id)")
    link = _issue_link(db=db, telegram_id=user_tid, platform=platform, region=region, request=request)
    return OneClickResponse(link=link)

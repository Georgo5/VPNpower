from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import User
from ..security_jwt import make_subscription_token
from ..settings import settings

router = APIRouter(tags=["users"])


# ====== Schemas ======

class RegisterIn(BaseModel):
    tg_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserOut(BaseModel):
    id: int
    tg_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    plan_devices: int
    subscription_end_at: Optional[str]
    subscription_active: bool

    model_config = ConfigDict(from_attributes=True)


# ====== Handlers ======

@router.post("/users/register", response_model=UserOut)
def register_user(body: RegisterIn, db: Session = Depends(get_db)):
    """
    Регистрирует (или обновляет) пользователя.
    - При первом заходе выдаём триал на settings.TRIAL_DAYS.
    - Лимит устройств ставим равным settings.SUB_MAX_DEVICES (можете менять дальше тарифами).
    - Поддерживаем обновление username/имени/фамилии.
    """
    u: Optional[User] = db.query(User).filter(User.tg_id == body.tg_id).first()

    if u is None:
        u = User(
            tg_id=body.tg_id,
            tg_username=body.username,
            first_name=body.first_name,
            last_name=body.last_name,
            plan_devices=settings.SUB_MAX_DEVICES,  # дефолтный лимит устройств
            subscription_active=True,
            subscription_end_at=utcnow() + timedelta(days=settings.TRIAL_DAYS),  # триал
        )
        u.ensure_uuid()  # legacy per-user UUID
        db.add(u)
        db.commit()
        db.refresh(u)
    else:
        changed = False
        # Обновляем публичные поля, если изменились
        if body.username is not None and u.tg_username != body.username:
            u.tg_username = body.username
            changed = True
        if body.first_name is not None and u.first_name != body.first_name:
            u.first_name = body.first_name
            changed = True
        if body.last_name is not None and u.last_name != body.last_name:
            u.last_name = body.last_name
            changed = True

        # Если по историческим причинам триал не проставлен — запускаем мягко
        if u.subscription_end_at is None:
            u.subscription_active = True
            u.subscription_end_at = utcnow() + timedelta(days=settings.TRIAL_DAYS)
            changed = True

        if changed:
            u.updated_at = utcnow()
            db.add(u)
            db.commit()
            db.refresh(u)

    # Возвращаем явно — чтобы корректно вывести username из tg_username
    return UserOut(
        id=u.id,
        tg_id=u.tg_id,
        username=u.tg_username,
        first_name=u.first_name,
        last_name=u.last_name,
        plan_devices=u.plan_devices,
        subscription_end_at=u.subscription_end_at.isoformat() if u.subscription_end_at else None,
        subscription_active=bool(u.subscription_active),
    )


@router.get("/debug/sub_token/{tg_id}")
def debug_sub_token(tg_id: int, db: Session = Depends(get_db)):
    """
    Отладочный эндпоинт: выпускает JWT-подписку старого формата для совместимости с /sub/vless.
    В проде опираемся на one-click токены (/api/oneclick + /sub/{token}).
    """
    u: Optional[User] = db.query(User).filter(User.tg_id == tg_id).first()
    if not u:
        raise HTTPException(404, "user not found")
    token = make_subscription_token(u.id, u.token_version, ttl_hours=24 * 30)
    return {"token": token}

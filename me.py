# backend/routers/me.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import exc as sa_exc, select, func, inspect as sa_inspect

from ..db import get_db
from ..models import User, Device
from ..schemas import MeResponse
from ..settings import settings

router = APIRouter()  # подключается в main.py с prefix="/api"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ceil_days_left(end_at: Optional[datetime]) -> int:
    if not end_at:
        return 0
    delta = (end_at - _utcnow()).total_seconds()
    if delta <= 0:
        return 0
    return int(delta // 86400) + (1 if (delta % 86400) > 0 else 0)


def _count_devices(db: Session, user_id: int) -> int:
    """Безопасный подсчёт устройств: учитываем разные схемы таблицы и делаем rollback при ошибке."""
    try:
        insp = sa_inspect(db.bind)
        cols = {c["name"] for c in insp.get_columns("devices")}
    except Exception:
        cols = set()
    has_status = "status" in cols

    try:
        if has_status:
            stmt = (
                select(func.count())
                .select_from(Device)
                .where(Device.user_id == user_id, Device.status == "active")
            )
        else:
            stmt = select(func.count()).select_from(Device).where(Device.user_id == user_id)
        return int(db.execute(stmt).scalar() or 0)
    except sa_exc.SQLAlchemyError:
        db.rollback()
        try:
            stmt = select(func.count()).select_from(Device).where(Device.user_id == user_id)
            return int(db.execute(stmt).scalar() or 0)
        except Exception:
            return 0


@router.get("/me", response_model=MeResponse)
def get_me(
    telegram_id: Optional[int] = Query(None, description="Telegram user id (preferred)"),
    tg_id: Optional[int] = Query(None, description="Alias for telegram_id"),
    db: Session = Depends(get_db),
) -> MeResponse:
    """
    Возвращает сводку для «Личного кабинета»:
    active, plan (trial/pro/expired), days_left, devices/max_devices, bonus, trial_days.
    """
    user_tid = telegram_id or tg_id
    if not user_tid:
        raise HTTPException(status_code=400, detail="telegram_id (or tg_id) is required")

    user = db.query(User).filter(User.tg_id == user_tid).first()
    if not user:
        # создаём «пустого» пользователя — триал выдаём при первом "Подключить"
        user = User(tg_id=user_tid, subscription_active=False, subscription_end_at=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    now = _utcnow()

    # Активная подписка — флаг + неистёкшая дата
    active = bool(user.subscription_active and user.subscription_end_at and user.subscription_end_at > now)
    days_left = _ceil_days_left(user.subscription_end_at)

    # План: trial/pro/expired
    plan = "expired"
    if active:
        trial_end = (user.created_at or now) + timedelta(days=settings.TRIAL_DAYS)
        plan = "trial" if (user.subscription_end_at and user.subscription_end_at <= trial_end) else "pro"

    devices_cnt = _count_devices(db, user.id)

    # Лимит устройств берём из профиля пользователя (device_slots → plan_devices), иначе из настроек
    max_devices = int(getattr(user, "plan_devices", None) or settings.SUB_MAX_DEVICES)

    return MeResponse(
        active=active,
        plan=plan,                 # "trial" | "pro" | "expired"
        days_left=days_left,
        bonus=0,                   # рефералку подключим позже
        devices=devices_cnt,
        max_devices=max_devices,
        trial_days=settings.TRIAL_DAYS,
    )

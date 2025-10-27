# backend/schemas.py
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

# =========================
# Общие типы / перечисления
# =========================
Platform = Literal["ios", "android", "windows", "mac", "linux", "other"]
Plan = Literal["trial", "pro", "expired"]
DeviceStatus = Literal["active", "blocked", "evicted"]


# =========================
# One‑click подписка (API)
# =========================
class OneClickRequest(BaseModel):
    """
    Запрос на получение подписочной ссылки.
    """
    telegram_id: int = Field(..., description="Telegram ID пользователя")
    platform: Platform = Field(..., description="Платформа клиента (для мягкой фильтрации нод)")
    region: Optional[str] = Field(
        default=None,
        description="Желаемый регион (например, 'EU', 'SE', 'FI'). По умолчанию auto."
    )


class OneClickResponse(BaseModel):
    """
    Ответ с единой ссылкой подписки.
    """
    link: str


# =========================
# Личный кабинет (API /api/me)
# =========================
class MeResponse(BaseModel):
    """
    Сводка для личного кабинета/бота.
    """
    active: bool
    plan: str            # "trial" | "pro" | "expired"
    days_left: int
    bonus: int
    devices: int
    max_devices: int
    trial_days: int

    model_config = ConfigDict(from_attributes=True)


# ======================================
# Устройства (слоты) — новые DTO (MVP)
# ======================================
class DeviceSlotOut(BaseModel):
    """
    Описание слота устройства (используется в экранах «Управление устройствами»).
    """
    id: int
    device_key: str
    status: DeviceStatus
    platform: Optional[Platform] = None
    uuid: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    last_seen_ip: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# Legacy/совместимость (оставлено, если где-то используется)
# =====================================================
# === Users (legacy) ===
class UserCreate(BaseModel):
    tg_id: str


class UserOut(BaseModel):
    id: int
    tg_id: str
    device_slots: int
    trial_used: bool
    trial_end: Optional[str] = None
    expires_at: Optional[str] = None
    bonus_cents: int

    model_config = ConfigDict(from_attributes=True)


# === Devices (legacy, если где-то ожидается label/region) ===
class DeviceCreate(BaseModel):
    user_id: int
    label: str = "Device"
    region: str = "EU"


class DeviceOut(BaseModel):
    id: int
    user_id: int
    label: str
    region: str

    model_config = ConfigDict(from_attributes=True)

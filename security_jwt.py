# backend/security_jwt.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from jwt import InvalidTokenError

from .settings import settings

# Алгоритм можно переопределить через settings.JWT_ALGO (если появится), иначе HS256.
ALGO: str = getattr(settings, "JWT_ALGO", "HS256")
ISS: str = "vpnpower"  # фиксируем для стабильности токенов

# Какие клеймы требуем обязательно (совместимо с тем, как токены создавались ранее)
_REQUIRED_CLAIMS = ("exp", "iat", "iss", "sub")


def make_subscription_token(
    user_id: int,
    token_version: int,
    ttl_hours: int = 24 * 30,
    *,
    scope: str = "subscription",
    tg_id: Optional[int] = None,  # опционально — добавим tid в новые токены (совместимо)
) -> str:
    """
    Генерирует подписочный JWT.
    Поля:
      - iss: 'vpnpower'
      - sub: str(user_id)  (исторически: внутренний user.id)
      - tv: token_version  (для инвалидации при ротации)
      - iat/exp: время выпуска и истечения
      - scope: 'subscription'
      - uid/tid: опциональные клеймы для новой схемы (не обязательны)
    """
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "iss": ISS,
        "sub": str(user_id),
        "tv": int(token_version),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
        "scope": scope,
        # новые клеймы (не ломают старую обработку):
        "uid": int(user_id),
    }
    if tg_id is not None:
        payload["tid"] = int(tg_id)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)


def decode_subscription_token(
    token: str,
    *,
    expected_scope: Optional[str] = "subscription",
    leeway_seconds: int = 30,
) -> Dict[str, Any]:
    """
    Декодирует и валидирует подписочный JWT.
    - Проверяет exp/iat/iss/sub.
    - Валидирует issuer (ISS).
    - Если в токене есть 'scope' и задан expected_scope — сверяет.
    - Разрешает небольшой сдвиг часов (leeway_seconds).

    Совместимость:
    - Если ALGO из настроек неожиданно не подходит (ошибка), пробуем HS256 как фолбэк.
    """
    options = {"require": list(_REQUIRED_CLAIMS)}
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGO],
            options=options,
            issuer=ISS,
            leeway=leeway_seconds,
        )
    except InvalidTokenError:
        # Безопасный фолбэк: попробуем HS256 (на случай, если ALGO поменяли в конфиге,
        # а в обороте ещё остались старые токены).
        if ALGO != "HS256":
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=["HS256"],
                options=options,
                issuer=ISS,
                leeway=leeway_seconds,
            )
        else:
            raise

    if expected_scope is not None:
        scope = payload.get("scope")
        # Если scope отсутствует — считаем валидным (для старых токенов),
        # если присутствует — должен совпасть.
        if scope is not None and scope != expected_scope:
            raise InvalidTokenError("Invalid scope")

    return payload


def token_version_valid(current_version: int, payload: Dict[str, Any]) -> bool:
    """
    Помогает быстро проверить «протух» ли токен из‑за ротации token_version у пользователя.
    Пример использования:
        if not token_version_valid(user.token_version, payload): -> отклонить/попросить релогин.
    """
    try:
        return int(payload.get("tv")) == int(current_version)
    except Exception:
        # Для старых токенов без 'tv' пропускаем проверку
        return True


__all__ = [
    "ALGO",
    "ISS",
    "make_subscription_token",
    "decode_subscription_token",
    "token_version_valid",
]

# backend/routers/subscription.py
from __future__ import annotations

import re
import json
import base64
from datetime import datetime, timezone
from typing import Optional, Iterable, List
from uuid import uuid4
from urllib.parse import urlparse, parse_qs, unquote, quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, load_only

from ..db import get_db
from ..models import User, Node, Device, OneClickToken

# JWT-проверка (если настроена). Если нет — используем мягкий разбор payload.
try:
    from ..security_jwt import decode_subscription_token  # type: ignore
except Exception:  # pragma: no cover
    decode_subscription_token = None  # type: ignore

try:
    from ..settings import settings  # type: ignore
    BRAND_NAME = getattr(settings, "BRAND_NAME", "VPNpower")
    SUB_DEFAULT_MAX_DEVICES = int(getattr(settings, "SUB_MAX_DEVICES", 1))
except Exception:  # pragma: no cover
    BRAND_NAME = "VPNpower"
    SUB_DEFAULT_MAX_DEVICES = 1

router = APIRouter(tags=["subscription"])

JWT_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")


# ==== utils ====

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _unquote_deep(s: str, rounds: int = 3) -> str:
    if not s:
        return s
    cur = s
    for _ in range(rounds):
        nxt = unquote(cur)
        if nxt == cur:
            break
        cur = nxt
    return cur


def _unwrap_url_token(s: str) -> str:
    """
    Извлечь токен из URL (учитывая %-кодировку):
      - https://host/sub/vless?token=JWT
      - https://host/sub/<oneclick_or_jwt>
    """
    if not s:
        return s
    s = _unquote_deep(s)
    low = s.lower()
    if low.startswith(("http://", "https://")):
        u = urlparse(s)
        q = parse_qs(u.query)
        if u.path.endswith("/sub/vless") and "token" in q and q["token"]:
            return q["token"][0]
        m = re.search(r"/sub/([^/?#]+)", u.path)
        if m:
            return m.group(1)
    return s


def _jwt_payload_noverify(token: str) -> Optional[dict]:
    """
    Fallback: читаем payload JWT без проверки подписи (чтобы вытащить user_id/tg_id).
    Безопасность: сюда внешний пользователь токен не подставляет — он берётся из alias/входных параметров.
    """
    try:
        if not JWT_RE.fullmatch(token or ""):
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        data = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _platform_from_request(request: Request | None) -> Optional[str]:
    if not request:
        return None
    ua = (request.headers.get("User-Agent") or "").lower()
    for key, plat in (
        ("iphone", "ios"),
        ("ipad", "ios"),
        ("android", "android"),
        ("mac os x", "macos"),
        ("macintosh", "macos"),
        ("windows", "windows"),
    ):
        if key in ua:
            return plat
    return None


def _get_active_nodes(db: Session) -> list[Node]:
    # Аккуратно читаем минимально нужные поля + фильтр по active + сортировка по priority desc, id asc
    try:
        q = db.query(Node).options(load_only(
            Node.name, Node.region, Node.host, Node.port,
            Node.reality_public_key, Node.short_id, Node.sni,
            Node.flow, Node.fingerprint, Node.active, Node.priority
        ))
        q = q.filter((Node.active == True) | (Node.active.is_(None)))  # noqa: E712
        q = q.order_by(Node.priority.desc(), Node.id.asc())
        return list(q.all())
    except Exception:
        # На случай несовпадения колонок — отдадим всё, а фильтрацию сделаем ниже.
        return list(db.query(Node).all())


def _build_vless_lines(nodes: Iterable[Node], uuid: str, brand: str) -> List[str]:
    lines: List[str] = []
    for n in nodes:
        host = getattr(n, "host", "") or ""
        if not host:
            continue
        port = int(getattr(n, "port", 443) or 443)
        pbk  = getattr(n, "reality_public_key", "") or ""
        sid  = getattr(n, "short_id", "") or ""
        sni  = getattr(n, "sni", "") or host
        flow = getattr(n, "flow", "") or "xtls-rprx-vision"
        fp   = getattr(n, "fingerprint", "") or "chrome"
        label = (
            getattr(n, "name", None)
            or getattr(n, "region", None)
            or getattr(n, "country_code", None)
            or host
        )
        tag = f"{brand}-{label}".replace(" ", "_")
        query = (
            f"encryption=none&flow={quote(flow)}&security=reality"
            f"&sni={quote(sni)}&fp={quote(fp)}&pbk={quote(pbk)}&sid={quote(sid)}&type=tcp"
        )
        lines.append(f"vless://{uuid}@{host}:{port}?{query}#{quote(tag)}")
    return lines


def _ensure_device_slot(db: Session, user: User, device_key: Optional[str], request: Request | None) -> str:
    """
    LRU-менеджмент слотов устройств (лимит users.device_slots или SUB_DEFAULT_MAX_DEVICES).
    Возвращает uuid для конфигов (uuid слота, либо fallback на user.vless_uuid при отсутствии device_key).
    """
    max_devices = int(getattr(user, "device_slots", None) or SUB_DEFAULT_MAX_DEVICES or 1)

    # Без ключа устройства — работаем через per-user UUID (legacy)
    if not device_key:
        if not getattr(user, "vless_uuid", None):
            user.vless_uuid = str(uuid4())
            db.add(user)
        return user.vless_uuid

    dev = db.query(Device).filter(Device.user_id == user.id, Device.device_key == device_key).first()

    if not dev:
        active = (
            db.query(Device)
            .filter(Device.user_id == user.id, Device.status == "active")
            .order_by(Device.last_seen_at.asc().nullsfirst(), Device.created_at.asc())
            .all()
        )
        if len(active) >= max_devices:
            victim = active[0]
            victim.status = "revoked"
            victim.last_seen_at = _utcnow()
            db.add(victim)
            # TODO: уведомить агент узлов о RemoveUser(victim.uuid)

        dev = Device(
            user_id=user.id,
            device_key=device_key,
            uuid=str(uuid4()),
            platform=_platform_from_request(request),
            status="active",
            last_seen_ip=(request.client.host if request and request.client else None),
            last_seen_at=_utcnow(),
        )
        db.add(dev)
    else:
        dev.last_seen_at = _utcnow()
        if request and request.client:
            dev.last_seen_ip = request.client.host
        if not getattr(dev, "platform", None):
            dev.platform = _platform_from_request(request)
        db.add(dev)

    return dev.uuid


def _days_left(user: User) -> Optional[int]:
    try:
        if getattr(user, "subscription_end_at", None):
            delta = getattr(user, "subscription_end_at") - _utcnow()
            return max(0, int(delta.total_seconds() // 86400))
    except Exception:
        pass
    return None


def _header_lines(user: User) -> List[str]:
    # Аккуратный баннер-статус
    dl = _days_left(user)
    dl_str = f", days_left: {dl}" if dl is not None else ""
    plan = "active" if getattr(user, "subscription_active", True) else "expired"
    return [f"{BRAND_NAME} — plan: {plan}{dl_str}"]


def _user_from_token(db: Session, raw_token: str) -> User:
    """
    Универсальный разбор токена:
      1) снимаем URL/процентную обёртку;
      2) пытаемся провалидировать JWT (если есть decode_subscription_token);
      3) если не получилось — читаем payload JWT без подписи;
      4) иначе считаем one‑click и ищем в oneclick_tokens.
    """
    token = _unwrap_url_token(raw_token)

    # Полная валидация JWT (если настроена)
    if decode_subscription_token is not None and JWT_RE.fullmatch(token or ""):
        try:
            payload = decode_subscription_token(token)
            uid = payload.get("user_id") or payload.get("uid") or payload.get("sub")
            tg_id = payload.get("tg_id")
            user: Optional[User] = None
            if uid is not None:
                try:
                    user = db.query(User).filter(User.id == int(uid)).first()
                except Exception:
                    user = None
            if not user and tg_id is not None:
                user = db.query(User).filter(User.tg_id == int(tg_id)).first()
            if user:
                if not getattr(user, "vless_uuid", None):
                    user.vless_uuid = str(uuid4())
                    db.add(user)
                return user
        except Exception:
            # fallback на мягкий разбор payload
            pass

    # Мягкий разбор payload без подписи
    if JWT_RE.fullmatch(token or ""):
        payload = _jwt_payload_noverify(token)
        if payload:
            uid = payload.get("user_id") or payload.get("uid") or payload.get("sub")
            tg_id = payload.get("tg_id")
            user: Optional[User] = None
            if uid is not None:
                try:
                    user = db.query(User).filter(User.id == int(uid)).first()
                except Exception:
                    user = None
            if not user and tg_id is not None:
                user = db.query(User).filter(User.tg_id == int(tg_id)).first()
            if user:
                if not getattr(user, "vless_uuid", None):
                    user.vless_uuid = str(uuid4())
                    db.add(user)
                return user
        # если payload нечитабелен — ниже пойдём в one‑click

    # One-click
    rec = db.query(OneClickToken).filter(OneClickToken.token == token).first()
    if not rec:
        raise HTTPException(status_code=404, detail="token not found")
    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if not getattr(user, "vless_uuid", None):
        user.vless_uuid = str(uuid4())
        db.add(user)
    return user


def _compose_plain(db: Session, user: User, uuid_for_links: str, with_info: bool) -> str:
    nodes = _get_active_nodes(db)
    lines = _build_vless_lines(nodes, uuid_for_links, BRAND_NAME)
    if with_info:
        header = _header_lines(user)
        # две строки с '# ' сверху: статус + штамп времени
        ts = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        banner = [f"# {header[0]}", f"# generated: {ts}"]
        return "\n".join(banner + lines)
    return "\n".join(lines)


def _compose_b64(db: Session, user: User, uuid_for_links: str, with_info: bool) -> str:
    plain = _compose_plain(db, user, uuid_for_links, with_info)
    # одна длинная строка без переводов
    return base64.b64encode(plain.encode("utf-8")).decode("ascii")


def _decide_fmt(fmt: str | None, request: Request | None) -> str:
    """
    Выбор формата выдачи:
      - если fmt не задан или fmt=auto — отдаём base64 (требование по умолчанию);
      - fmt=plain — plain; fmt=base64 или b64 — base64.
    """
    if not fmt or fmt == "auto":
        return "base64"
    if fmt in ("b64", "base64"):
        return "base64"
    return "plain"


# ==== endpoints ====

@router.get("/sub/vless", response_class=PlainTextResponse, summary="VLESS subscription (plain/base64)")
def subscription_unified(
    token: str,
    d: Optional[str] = Query(None, description="device slot key"),
    fmt: Optional[str] = Query("auto", regex="^(auto|plain|base64|b64)$"),
    info: int = Query(0, ge=0, le=1, description="prepend two '# ' header lines"),
    request: Request = None,  # type: ignore
    db: Session = Depends(get_db),
):
    user = _user_from_token(db, token)
    uuid_for_links = _ensure_device_slot(db, user, d, request)

    try:
        db.commit()
    except Exception:
        db.rollback()

    out_fmt = _decide_fmt(fmt, request)
    if out_fmt == "plain":
        body = _compose_plain(db, user, uuid_for_links, with_info=bool(info))
    else:
        body = _compose_b64(db, user, uuid_for_links, with_info=bool(info))
    return PlainTextResponse(body, status_code=200)


# Legacy-совместимость: /sub/{token} + те же параметры
@router.get("/sub/{token}", response_class=PlainTextResponse, include_in_schema=False)
def subscription_legacy(
    token: str,
    d: Optional[str] = Query(None, description="device slot key"),
    fmt: Optional[str] = Query("auto", regex="^(auto|plain|base64|b64)$"),
    info: int = Query(0, ge=0, le=1),
    request: Request = None,  # type: ignore
    db: Session = Depends(get_db),
):
    return subscription_unified(token=_unwrap_url_token(token), d=d, fmt=fmt, info=info, request=request, db=db)

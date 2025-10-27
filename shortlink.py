from __future__ import annotations

import os
import re
import secrets
import string
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import create_engine, text

try:
    from ..db import engine as shared_engine  # type: ignore
    engine = shared_engine
except Exception:  # pragma: no cover
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(db_url, pool_pre_ping=True)

router = APIRouter(tags=["shortlink"])

ALIAS_RE = re.compile(r"^[A-Za-z0-9]{8,12}$")
JWT_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")


def _gen_alias(n: int = 9) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


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


def _dissect_input(raw: str) -> Tuple[str, str]:
    raw = (raw or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="empty token")

    if raw.startswith("jwt:") or raw.startswith("oc:"):
        kind, val = raw.split(":", 1)
        return kind, _unwrap_url_token(val)

    if raw.lower().startswith(("http://", "https://")):
        val = _unwrap_url_token(raw)
        if JWT_RE.fullmatch(val):
            return "jwt", val
        return "oc", val

    if JWT_RE.fullmatch(raw):
        return "jwt", raw

    return "oc", _unwrap_url_token(raw)


def _stored_token(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def get_or_create_alias_for_token(raw_token: str, user_id: Optional[int] = None) -> str:
    kind, value = _dissect_input(raw_token)
    stored = _stored_token(kind, value)

    with engine.begin() as conn:
        if user_id is None and kind == "oc":
            try:
                uid = conn.execute(
                    text("SELECT user_id FROM oneclick_tokens WHERE token = :t ORDER BY id DESC LIMIT 1"),
                    {"t": value},
                ).scalar()
                if uid is not None:
                    user_id = int(uid)
            except Exception:
                pass

        if user_id is not None:
            conn.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": int(user_id)})
            a = conn.execute(
                text("SELECT alias FROM short_links WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"),
                {"u": int(user_id)},
            ).scalar()
            if a:
                conn.execute(
                    text("UPDATE short_links SET token = :t, created_at = now() WHERE alias = :a"),
                    {"t": stored, "a": a},
                )
                return str(a)

        a2 = conn.execute(text("SELECT alias FROM short_links WHERE token = :t LIMIT 1"), {"t": stored}).scalar()
        if a2:
            if user_id is not None:
                conn.execute(
                    text("UPDATE short_links SET user_id = COALESCE(user_id, :u) WHERE alias = :a"),
                    {"u": int(user_id), "a": a2},
                )
            return str(a2)

        for _ in range(10):
            alias = _gen_alias(9)
            exists = conn.execute(text("SELECT 1 FROM short_links WHERE alias = :a"), {"a": alias}).scalar()
            if not exists:
                conn.execute(
                    text("INSERT INTO short_links(alias, token, user_id, created_at) VALUES (:a, :t, :u, now())"),
                    {"a": alias, "t": stored, "u": user_id},
                )
                return alias

    raise HTTPException(status_code=500, detail="unable to allocate alias")


@router.post("/api/alias/create")
def api_alias_create(token: str = Query(...), user_id: Optional[int] = Query(None)):
    alias = get_or_create_alias_for_token(token, user_id=user_id)
    return {"alias": alias, "user_id": user_id, "reused": True}


@router.get("/s/{alias}", response_class=PlainTextResponse)
def s_alias(
    alias: str,
    d: Optional[str] = Query(None),
    fmt: Optional[str] = Query(None),    # <— принимаем
    info: Optional[bool] = Query(None),  # <— принимаем
    name: Optional[str] = Query(None),
):
    alias = (alias or "").strip()
    if not ALIAS_RE.fullmatch(alias):
        raise HTTPException(status_code=404, detail="bad alias")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT token FROM short_links WHERE alias = :a LIMIT 1"),
            {"a": alias},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="alias not found")

        stored = row[0]
        if ":" in stored:
            kind, value = stored.split(":", 1)
        else:
            kind, value = _dissect_input(stored)

    timeout = httpx.Timeout(timeout=10.0, connect=5.0)
    params = {"token": value}
    if d:
        params["d"] = d
    if fmt in ("plain", "base64"):
        params["fmt"] = fmt
    if info in (True, "1", "true", "yes"):
        params["info"] = "1"
    if name:
        params["name"] = name[:32]

    try:
        r = httpx.get(
            url="http://127.0.0.1:8000/sub/vless",
            params=params,
            timeout=timeout,
        )
        r.raise_for_status()
        return PlainTextResponse(r.text, status_code=r.status_code)

    except httpx.HTTPStatusError as e:
        # Проксируем ответ и код ошибки внутреннего бэкенда (например 401/404)
        return PlainTextResponse(e.response.text, status_code=e.response.status_code)

    except httpx.HTTPError as e:
        # Сетевые/транспортные ошибки до апстрима
        raise HTTPException(status_code=502, detail=f"backend error for /sub/vless: {e}")

# /srv/vpnpower/app/vpn-subscription-starter/backend/routers/node_sync.py
from __future__ import annotations

import os
from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import exists, and_  # <-- ВАЖНО: нужны для "мягкого" fallback

from ..db import get_db
from ..models import Device, User

router = APIRouter(tags=["node-sync"])

NODE_SYNC_SECRET = (os.getenv("NODE_SYNC_SECRET") or "").strip()

@router.get("/api/nodes/active-uuids")
def api_nodes_active_uuids(
    secret: str = Query(..., description="shared secret"),
    inbound_tag: str = Query("vless-reality-in"),
    flow: str = Query("xtls-rprx-vision"),
    db: Session = Depends(get_db),
):
    if not NODE_SYNC_SECRET or secret.strip() != NODE_SYNC_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")

    # 1) Все активные device-UUID’ы
    uuids: List[str] = [u for (u,) in db.query(Device.uuid).filter(Device.status == "active").all() if u]

    # 2) МЯГКИЙ fallback: добавим users.vless_uuid ТОЛЬКО тем,
    #    у кого нет ни одного активного устройства.
    has_active = exists().where(and_(Device.user_id == User.id, Device.status == "active"))
    extra = [u for (u,) in db.query(User.vless_uuid)
             .filter(User.vless_uuid.isnot(None))
             .filter(~has_active)
             .all()]
    for x in extra:
        if x and x not in uuids:
            uuids.append(x)

    return {"inbound_tag": inbound_tag, "flow": flow, "uuids": sorted(set(uuids))}

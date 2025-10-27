# backend/routers/devices.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..routers.db import get_db
from ..models import User, Device
from ..schemas import DeviceCreate, DeviceOut

router = APIRouter(prefix="/devices", tags=["devices"])

@router.post("", response_model=DeviceOut)
def create_device(data: DeviceCreate, db: Session = Depends(get_db)):
    u = db.query(User).get(data.user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")

    used = db.query(Device).filter(Device.user_id == u.id).count()
    if used >= u.device_slots:
        raise HTTPException(status_code=409, detail="no free device slots")

    d = Device(user_id=u.id, label=data.label, region=data.region)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d

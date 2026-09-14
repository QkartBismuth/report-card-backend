from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Device, ErrorLog, User
from schemas import DeviceRegister, ErrorCreate

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/device")
def register_device(
    data: DeviceRegister,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    device = db.query(Device).filter(Device.device_id == data.device_id).first()
    ip = request.client.host if request.client else None
    if device:
        device.platform = data.platform
        device.model = data.model
        device.manufacturer = data.manufacturer
        device.os_version = data.os_version
        device.app_version = data.app_version
        device.ip = ip
        device.user_id = user.id
    else:
        device = Device(
            device_id=data.device_id,
            platform=data.platform,
            model=data.model,
            manufacturer=data.manufacturer,
            os_version=data.os_version,
            app_version=data.app_version,
            ip=ip,
            user_id=user.id,
        )
        db.add(device)
    db.commit()
    return {"ok": True}


@router.post("/error")
def report_error(
    data: ErrorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.add(
        ErrorLog(
            device_id=data.device_id,
            app_version=data.app_version,
            message=data.message[:4000],
            stack=(data.stack or "")[:8000] or None,
        )
    )
    db.commit()
    return {"ok": True}
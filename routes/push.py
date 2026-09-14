from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User, get_config
from schemas import PushConfigOut

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/config", response_model=PushConfigOut)
def push_config(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        version = int(get_config(db, "config_version", "1"))
    except (TypeError, ValueError):
        version = 1
    return PushConfigOut(
        version=version,
        server_url=get_config(db, "server_url"),
        wifi_ssid=get_config(db, "wifi_ssid"),
        wifi_password=get_config(db, "wifi_password"),
    )
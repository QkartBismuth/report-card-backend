from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Group, User
from schemas import GroupOut
from services.visibility import visible_groups

router = APIRouter(prefix="/groups", tags=["groups"])


def _to_out(g: Group) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "year": g.year,
        "curator_id": g.curator_id,
        "curator_name": g.curator.full_name if g.curator else None,
    }


@router.get("", response_model=list[GroupOut])
def list_groups(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return [_to_out(g) for g in visible_groups(db, user)]


@router.get("/{group_id}", response_model=GroupOut)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if group not in visible_groups(db, user):
        raise HTTPException(status_code=403, detail="Нет доступа к группе")
    return _to_out(group)
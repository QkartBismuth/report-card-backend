from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, require_monitor, require_teacher
from database import get_db
from models import Subject, User, UserRole
from schemas import SubjectCreate, SubjectOut, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _to_out(s: Subject) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "teacher_id": s.teacher_id,
        "teacher_name": s.teacher.full_name if s.teacher else None,
    }


@router.get("", response_model=list[SubjectOut])
def list_subjects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Subject).order_by(Subject.name)
    if user.role == UserRole.teacher:
        # предметник видит только свои предметы
        q = q.filter(Subject.teacher_id == user.id)
    return [_to_out(s) for s in q.all()]


@router.post("", response_model=SubjectOut)
def add_subject(
    data: SubjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название пустое")
    exists = db.query(Subject).filter(Subject.name.ilike(name)).first()
    if exists:
        if user.role == UserRole.teacher:
            exists.teacher_id = user.id
            db.commit()
        return _to_out(exists)
    s = Subject(name=name, teacher_id=user.id if user.role == UserRole.teacher else None)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.patch("/{subject_id}", response_model=SubjectOut)
def update_subject(
    subject_id: int,
    data: SubjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in (UserRole.teacher, UserRole.admin):
        raise HTTPException(status_code=403, detail="Нет прав на назначение предмета")
    s = db.get(Subject, subject_id)
    if not s:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    if data.teacher_id is not None:
        target = db.get(User, data.teacher_id)
        if not target or target.role != UserRole.teacher:
            raise HTTPException(status_code=400, detail="Преподаватель не найден")
        s.teacher_id = data.teacher_id
    else:
        s.teacher_id = None
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == UserRole.monitor:
        raise HTTPException(status_code=403, detail="Только преподаватель может удалить предмет")
    s = db.get(Subject, subject_id)
    if not s:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    db.delete(s)
    db.commit()
    return {"ok": True}
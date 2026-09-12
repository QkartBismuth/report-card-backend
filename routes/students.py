from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user, require_monitor
from database import get_db
from models import Group, Student, User
from schemas import StudentCreate, StudentOut

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=list[StudentOut])
def list_students(
    group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Student)
        .filter(Student.group_id == group_id)
        .order_by(Student.full_name)
        .all()
    )


@router.post("", response_model=StudentOut)
def add_student(
    group_id: int = Query(...),
    data: StudentCreate = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if user.group_id is not None and group.id != user.group_id:
        raise HTTPException(
            status_code=403, detail="Староста может управлять только своей группой"
        )
    name = data.full_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Имя не может быть пустым")
    db.add(Student(group_id=group_id, full_name=name))
    db.commit()
    return (
        db.query(Student)
        .filter(Student.group_id == group_id)
        .order_by(Student.id.desc())
        .first()
    )


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    if user.group_id is not None and student.group_id != user.group_id:
        raise HTTPException(
            status_code=403, detail="Староста может управлять только своей группой"
        )
    db.delete(student)
    db.commit()
    return {"ok": True}
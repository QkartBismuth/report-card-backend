from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user, require_monitor
from database import get_db
from models import Group, Student, User
from schemas import ApplyRaportRequest, UploadRaportResponse
from services.docx_parser import parse_raport

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/raport", response_model=UploadRaportResponse)
async def upload_raport(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Пожалуйста, загрузите файл .docx")

    content = await file.read()
    try:
        result = parse_raport(content)
    except Exception:
        raise HTTPException(status_code=422, detail="Не удалось разобрать файл рапортички")

    if not result["students"]:
        raise HTTPException(status_code=422, detail="В файле не найдены студенты")

    return UploadRaportResponse(
        group_name=result["group_name"],
        group_year=result["group_year"],
        students=result["students"],
        parsed_at="",
    )


@router.post("/raport/apply")
def apply_raport(
    data: ApplyRaportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    if not data.students:
        raise HTTPException(status_code=422, detail="Список студентов пуст")

    group = db.query(Group).filter(Group.name == data.group_name).first()
    if not group:
        group = Group(name=data.group_name, year=data.group_year)
        db.add(group)
        db.flush()
    else:
        group.year = data.group_year
        db.query(Student).filter(Student.group_id == group.id).delete()
        db.flush()

    for name in data.students:
        db.add(Student(group_id=group.id, full_name=name))

    if user.group_id is not None and user.group_id != group.id:
        db.query(User).filter(User.id == user.id).update({"group_id": group.id})
        user.group_id = group.id
    elif user.group_id is None:
        user.group_id = group.id

    db.commit()
    return {"group_id": group.id, "students_count": len(data.students)}
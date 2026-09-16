from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from auth import get_current_user
from database import get_db
from models import AttendanceSession, Group, User, UserRole
from services.exporter import (
    export_bytes,
    export_filename,
    generate_monthly_hours_xlsx,
)
from services.visibility import visible_groups

router = APIRouter(prefix="/export", tags=["export"])

VALID_FORMATS = {"pdf", "docx", "xlsx"}


def _download_headers(fname: str) -> dict:
    fname_q = quote(fname)
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{fname_q}"}


def _fmt_or_400(fmt: str) -> str:
    fmt = fmt.lower()
    if fmt not in VALID_FORMATS:
        raise HTTPException(status_code=400, detail="Формат должен быть pdf, docx или xlsx")
    return fmt


def _teacher_group(db: Session, user: User, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if group not in visible_groups(db, user):
        raise HTTPException(status_code=403, detail="Нет доступа к группе")
    return group


def _require_report_viewer(user: User):
    if user.role not in (
        UserRole.teacher,
        UserRole.department_head,
        UserRole.admin,
    ):
        raise HTTPException(
            status_code=403,
            detail="Только преподаватель или завотделения могут выгружать рапортички",
        )


@router.get("/session/{session_id}")
def export_session(
    session_id: int,
    fmt: str = Query("pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_report_viewer(user)
    fmt = _fmt_or_400(fmt)
    s = (
        db.query(AttendanceSession)
        .options(
            joinedload(AttendanceSession.group),
            joinedload(AttendanceSession.subject),
            joinedload(AttendanceSession.records),
        )
        .filter(AttendanceSession.id == session_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    allowed = s.group in visible_groups(db, user)
    if allowed and user.role == UserRole.teacher and s.group.curator_id != user.id:
        if s.subject is None or s.subject.teacher_id != user.id:
            allowed = False
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к сессии")
    data, media = export_bytes(db, s.group, [s], fmt)
    fname = export_filename(fmt, s.group, s.date, s.date)
    return Response(content=data, media_type=media, headers=_download_headers(fname))


@router.get("/group/{group_id}")
def export_group(
    group_id: int,
    date_from: date = Query(...),
    date_to: date = Query(...),
    fmt: str = Query("pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_report_viewer(user)
    fmt = _fmt_or_400(fmt)
    group = _teacher_group(db, user, group_id)
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="дата начала больше даты окончания")

    query = (
        db.query(AttendanceSession)
        .options(
            joinedload(AttendanceSession.subject),
            joinedload(AttendanceSession.records),
        )
        .filter(
            AttendanceSession.group_id == group_id,
            AttendanceSession.date >= date_from,
            AttendanceSession.date <= date_to,
        )
    )
    sessions = query.all()
    if user.role == UserRole.teacher and group.curator_id != user.id:
        sessions = [s for s in sessions if s.subject and s.subject.teacher_id == user.id]
    data, media = export_bytes(db, group, sessions, fmt)
    fname = export_filename(fmt, group, date_from, date_to)
    return Response(content=data, media_type=media, headers=_download_headers(fname))


@router.get("/month/{group_id}")
def export_month(
    group_id: int,
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ведомость учета часов, пропущенных студентами за месяц (куратор группы)."""
    _require_report_viewer(user)
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="Месяц должен быть от 1 до 12")
    group = _teacher_group(db, user, group_id)
    if user.role == UserRole.teacher and group.curator_id != user.id:
        raise HTTPException(
            status_code=403, detail="Месячный отчёт доступен куратору группы"
        )
    data = generate_monthly_hours_xlsx(db, group, year, month)
    fname = f"vedomost_{group.name}_{year}-{month:02d}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_download_headers(fname),
    )
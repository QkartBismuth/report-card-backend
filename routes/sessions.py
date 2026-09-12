from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from auth import get_current_user, require_monitor, require_teacher
from database import get_db
from models import (
    AttendanceRecord,
    AttendanceSession,
    Group,
    MarkValue,
    Student,
    User,
    UserRole,
)
from schemas import RecordUpdate, SessionCreate, SessionDetail, SessionOut, SessionUpdate
from services.visibility import can_access_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(s: AttendanceSession) -> dict:
    return {
        "id": s.id,
        "group_id": s.group_id,
        "group_name": s.group.name if s.group else None,
        "subject_id": s.subject_id,
        "subject_name": s.subject.name if s.subject else None,
        "date": s.date,
        "pair_number": s.pair_number,
        "confirmed": s.confirmed,
        "confirmed_at": s.confirmed_at,
        "created_at": s.created_at,
    }


@router.get("", response_model=list[SessionOut])
def list_sessions(
    group_id: int = Query(...),
    date_from: date = Query(None),
    date_to: date = Query(None),
    only_confirmed: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = (
        db.query(AttendanceSession)
        .options(
            joinedload(AttendanceSession.group),
            joinedload(AttendanceSession.subject),
        )
        .filter(AttendanceSession.group_id == group_id)
    )
    if user.role == UserRole.teacher:
        group = db.get(Group, group_id)
        if group is not None and group.curator_id != user.id:
            q = q.filter(AttendanceSession.subject.has(teacher_id=user.id))
    elif user.role == UserRole.monitor:
        if user.group_id is not None and group_id != user.group_id:
            raise HTTPException(
                status_code=403, detail="Староста видит только свою группу"
            )
    if date_from:
        q = q.filter(AttendanceSession.date >= date_from)
    if date_to:
        q = q.filter(AttendanceSession.date <= date_to)
    if only_confirmed:
        q = q.filter(AttendanceSession.confirmed.is_(True))
    q = q.order_by(AttendanceSession.date.desc(), AttendanceSession.pair_number.asc())
    return [_to_out(s) for s in q.all()]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = (
        db.query(AttendanceSession)
        .options(
            joinedload(AttendanceSession.group),
            joinedload(AttendanceSession.subject),
            joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
        )
        .filter(AttendanceSession.id == session_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if not can_access_session(db, user, s):
        raise HTTPException(status_code=403, detail="Нет доступа к сессии")
    out = _to_out(s)
    records = sorted(s.records, key=lambda r: (r.student.full_name or ""))
    out["records"] = [
        {
            "id": r.id,
            "session_id": r.session_id,
            "student_id": r.student_id,
            "mark": r.mark.value,
        }
        for r in records
    ]
    return out


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    group = db.get(Group, data.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if user.group_id is not None and group.id != user.group_id:
        raise HTTPException(
            status_code=403, detail="Староста может создавать рапортички только для своей группы"
        )
    if user.group_id is not None and data.date != date.today():
        raise HTTPException(
            status_code=403, detail="Староста может создавать рапортички только за текущий день"
        )
    dup = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.group_id == data.group_id,
            AttendanceSession.date == data.date,
            AttendanceSession.pair_number == data.pair_number,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=409,
            detail="Сессия для этой пары в этот день уже существует",
        )
    s = AttendanceSession(
        group_id=data.group_id,
        subject_id=data.subject_id,
        date=data.date,
        pair_number=data.pair_number,
        created_by=user.id,
    )
    db.add(s)
    db.flush()
    for st in group.students:
        db.add(AttendanceRecord(session_id=s.id, student_id=st.id, mark=MarkValue.present))
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.put("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    data: SessionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.get(AttendanceSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if s.confirmed and user.role.value != "teacher":
        raise HTTPException(status_code=403, detail="Сессия уже подтверждена преподавателем")
    if data.subject_id is not None:
        s.subject_id = data.subject_id
    if data.date is not None:
        s.date = data.date
    if data.pair_number is not None:
        s.pair_number = data.pair_number
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.put("/{session_id}/records", response_model=SessionDetail)
def update_records(
    session_id: int,
    data: RecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_monitor),
):
    s = db.get(AttendanceSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if s.confirmed:
        raise HTTPException(status_code=403, detail="Сессия подтверждена преподавателем")

    student_ids = {st.id for st in db.query(Student.id).filter(Student.group_id == s.group_id)}
    for item in data.records:
        sid = item.get("student_id")
        mark_raw = item.get("mark")
        if sid not in student_ids:
            continue
        try:
            mark = MarkValue(mark_raw)
        except ValueError:
            continue
        rec = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == sid,
            )
            .first()
        )
        if rec:
            rec.mark = mark
        else:
            db.add(AttendanceRecord(session_id=session_id, student_id=sid, mark=mark))
    db.commit()
    return get_session(session_id, db, user)


def _teacher_can_manage(db, user, s) -> bool:
    if not can_access_session(db, user, s):
        raise HTTPException(status_code=403, detail="Нет доступа к сессии")
    return True


@router.post("/{session_id}/confirm", response_model=SessionDetail)
def confirm_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    s = db.get(AttendanceSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    _teacher_can_manage(db, user, s)
    s.confirmed = True
    s.confirmed_by = user.id
    s.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    return get_session(session_id, db, user)


@router.post("/{session_id}/unconfirm", response_model=SessionDetail)
def unconfirm_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    s = db.get(AttendanceSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    _teacher_can_manage(db, user, s)
    s.confirmed = False
    s.confirmed_by = None
    s.confirmed_at = None
    db.commit()
    return get_session(session_id, db, user)
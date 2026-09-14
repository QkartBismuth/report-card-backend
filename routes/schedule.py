from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from auth import get_current_user
from database import get_db
from models import (
    AttendanceRecord,
    AttendanceSession,
    Group,
    MarkValue,
    ScheduleEntry,
    Subject,
    User,
    UserRole,
)
from schemas import (
    CreateSessionsRequest,
    CreateSessionsResult,
    ScheduleEntryCreate,
    ScheduleEntryOut,
    ScheduleEntryUpdate,
    ScheduleImportRequest,
    ScheduleImportResult,
    ScheduleSourceSet,
)
from services import ktc
from services.schedule_import import (
    match_subject_by_name,
    match_teacher_by_surname,
)

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _can_view(db: Session, user: User, group: Group):
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.monitor:
        if user.group_id is None or group.id != user.group_id:
            raise HTTPException(status_code=403, detail="Староста видит только своё расписание")
        return True
    if group.curator_id == user.id:
        return True
    taught = (
        db.query(AttendanceSession.group_id)
        .join(Subject, AttendanceSession.subject_id == Subject.id)
        .filter(Subject.teacher_id == user.id, AttendanceSession.group_id == group.id)
        .first()
    )
    if taught:
        return True
    raise HTTPException(status_code=403, detail="Нет доступа к расписанию группы")


def _can_manage(db: Session, user: User, group: Group):
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.monitor and user.group_id is not None and group.id == user.group_id:
        return True
    raise HTTPException(status_code=403, detail="Нет прав на изменение расписания")


def _get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


def _to_out(e: ScheduleEntry) -> dict:
    return {
        "id": e.id,
        "group_id": e.group_id,
        "day_of_week": e.day_of_week,
        "pair_number": e.pair_number,
        "subject_id": e.subject_id,
        "subject_name": e.subject.name if e.subject else None,
        "teacher_id": e.teacher_id,
        "teacher_name": e.teacher_name,
        "teacher_full_name": e.teacher.full_name if e.teacher else None,
        "classroom": e.classroom,
        "time_start": e.time_start,
        "time_end": e.time_end,
        "cancelled": e.cancelled,
        "note": e.note,
    }


def _resolve_subject(db: Session, data, user: User) -> tuple[Subject | None, bool]:
    subject_id = getattr(data, "subject_id", None)
    if subject_id is not None:
        subject = db.get(Subject, subject_id)
        if not subject:
            raise HTTPException(status_code=400, detail="Предмет не найден")
        return subject, False
    name = getattr(data, "subject_name", None)
    if name:
        name = name.strip()
        if name:
            existing = db.query(Subject).filter(Subject.name.ilike(name)).first()
            if existing:
                return existing, False
            subject = Subject(name=name)
            db.add(subject)
            db.flush()
            return subject, True
    return None, False


def _match_teacher(db: Session, short_name: str, subject: Subject | None) -> tuple[User | None, int | None]:
    """Сопоставить краткое ФИО из расписания с аккаунтом преподавателя бэкенда."""
    if not short_name:
        return None, None
    teacher = match_teacher_by_surname(
        short_name, db.query(User).filter(User.role == UserRole.teacher).all()
    )
    teacher_id = teacher.id if teacher else None
    if teacher and subject is not None and subject.teacher_id is None:
        subject.teacher_id = teacher.id
    return teacher, teacher_id


@router.get("/{group_id}", response_model=list[ScheduleEntryOut])
def get_schedule(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = _get_group(db, group_id)
    _can_view(db, user, group)
    entries = (
        db.query(ScheduleEntry)
        .options(joinedload(ScheduleEntry.subject), joinedload(ScheduleEntry.teacher))
        .filter(ScheduleEntry.group_id == group_id)
        .order_by(ScheduleEntry.day_of_week, ScheduleEntry.pair_number)
        .all()
    )
    return [_to_out(e) for e in entries]


@router.put("/{group_id}/source", response_model=dict)
def set_source(
    group_id: int,
    data: ScheduleSourceSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = _get_group(db, group_id)
    _can_manage(db, user, group)
    if data.ktc_branch_id is not None:
        group.ktc_branch_id = data.ktc_branch_id
    if data.ktc_group_id is not None:
        group.ktc_group_id = data.ktc_group_id
    db.commit()
    return {"ok": True, "group_id": group.id,
            "ktc_branch_id": group.ktc_branch_id, "ktc_group_id": group.ktc_group_id}


@router.post("/{group_id}/import", response_model=ScheduleImportResult)
def import_schedule(
    group_id: int,
    data: ScheduleImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = _get_group(db, group_id)
    _can_manage(db, user, group)
    if not group.ktc_group_id:
        raise HTTPException(status_code=400, detail="Для группы не выбран источник КТК")
    try:
        week_data = ktc.fetch_timetable(group.ktc_group_id, data.week)
    except ktc.KtcError as e:
        raise HTTPException(status_code=502, detail=str(e))

    subjects = db.query(Subject).all()
    matched_keys = set()
    fetched_keys = set()
    subjects_created = []
    teachers_matched = []

    for day in week_data.get("days", []):
        day_num = ktc.day_of_week_num(day.get("title"))
        if not day_num:
            continue
        for lesson in day.get("lessons", []):
            t = lesson.get("time") or []
            if not t:
                continue
            try:
                pair = int(t[0])
            except (TypeError, ValueError):
                continue
            if pair < 1:
                continue
            fetched_keys.add((day_num, pair))
            subject, subject_created = _resolve_subject(
                db,
                type("S", (), {
                    "subject_name": lesson.get("title"),
                    "subject_id": None,
                })(),
                user,
            )
            if subject_created:
                subjects_created.append(subject.name)
            short_teacher = (lesson.get("teacher") or "").strip()
            teacher = None
            teacher_id = None
            if short_teacher:
                teacher, teacher_id = _match_teacher(db, short_teacher, subject)
                if teacher:
                    teachers_matched.append(short_teacher)
            classroom = (lesson.get("actual_classroom") or lesson.get("classroom") or "").strip()
            entry = (
                db.query(ScheduleEntry)
                .filter(
                    ScheduleEntry.group_id == group_id,
                    ScheduleEntry.day_of_week == day_num,
                    ScheduleEntry.pair_number == pair,
                )
                .first()
            )
            cancelled = bool(lesson.get("cancelled")) or lesson.get("status") == 1
            if entry:
                entry.subject_id = subject.id if subject else None
                entry.teacher_id = teacher_id
                entry.teacher_name = short_teacher
                entry.classroom = classroom
                if len(t) >= 3:
                    entry.time_start = t[1]
                    entry.time_end = t[2]
                entry.cancelled = cancelled
            else:
                entry = ScheduleEntry(
                    group_id=group_id,
                    day_of_week=day_num,
                    pair_number=pair,
                    subject_id=subject.id if subject else None,
                    teacher_id=teacher_id,
                    teacher_name=short_teacher,
                    classroom=classroom,
                    time_start=t[1] if len(t) >= 2 else None,
                    time_end=t[2] if len(t) >= 3 else None,
                    cancelled=cancelled,
                )
                db.add(entry)

    if data.replace:
        db.query(ScheduleEntry).filter(
            ScheduleEntry.group_id == group_id,
        ).filter(~((ScheduleEntry.day_of_week, ScheduleEntry.pair_number).in_(fetched_keys))).delete(synchronize_session="fetch")
    db.commit()

    count = db.query(ScheduleEntry).filter(ScheduleEntry.group_id == group_id).count()
    return ScheduleImportResult(
        group_id=group_id,
        week=data.week,
        entries_count=count,
        subjects_created=subjects_created,
        teachers_matched=teachers_matched,
    )


@router.post("/{group_id}/entries", response_model=ScheduleEntryOut, status_code=201)
def add_entry(
    group_id: int,
    data: ScheduleEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = _get_group(db, group_id)
    _can_manage(db, user, group)
    if not (1 <= data.day_of_week <= 7):
        raise HTTPException(status_code=422, detail="День недели должен быть 1..7")
    if data.pair_number < 1:
        raise HTTPException(status_code=422, detail="Номер пары должен быть >= 1")
    dup = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.group_id == group_id,
            ScheduleEntry.day_of_week == data.day_of_week,
            ScheduleEntry.pair_number == data.pair_number,
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail="Запись для этого дня и пары уже существует")
    subject = _resolve_subject(db, data, user)
    teacher = None
    teacher_id = None
    if data.teacher_name:
        teacher, teacher_id = _match_teacher(db, data.teacher_name.strip(), subject[0])
    entry = ScheduleEntry(
        group_id=group_id,
        day_of_week=data.day_of_week,
        pair_number=data.pair_number,
        subject_id=subject[0].id if subject[0] else None,
        teacher_id=teacher_id,
        teacher_name=(data.teacher_name or "").strip() or None,
        classroom=(data.classroom or "").strip() or None,
        cancelled=data.cancelled,
        note=data.note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


@router.patch("/{entry_id}", response_model=ScheduleEntryOut)
def update_entry(
    entry_id: int,
    data: ScheduleEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.get(ScheduleEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Запись расписания не найдена")
    group = db.get(Group, entry.group_id)
    _can_manage(db, user, group)
    if data.day_of_week is not None:
        if not (1 <= data.day_of_week <= 7):
            raise HTTPException(status_code=422, detail="День недели должен быть 1..7")
        entry.day_of_week = data.day_of_week
    if data.pair_number is not None:
        if data.pair_number < 1:
            raise HTTPException(status_code=422, detail="Номер пары должен быть >= 1")
        entry.pair_number = data.pair_number
    if data.subject_id is not None or data.subject_name is not None:
        subject, _ = _resolve_subject(db, data, user)
        entry.subject_id = subject.id if subject else None
        if subject and entry.teacher_id is None and entry.teacher_name:
            _, teacher_id = _match_teacher(db, entry.teacher_name, subject)
            entry.teacher_id = teacher_id
    if data.teacher_name is not None:
        entry.teacher_name = data.teacher_name.strip() or None
        subject = db.get(Subject, entry.subject_id) if entry.subject_id else None
        _, teacher_id = _match_teacher(db, entry.teacher_name, subject)
        entry.teacher_id = teacher_id
    if data.classroom is not None:
        entry.classroom = (data.classroom or "").strip() or None
    if data.cancelled is not None:
        entry.cancelled = data.cancelled
    if data.note is not None:
        entry.note = data.note or None
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.get(ScheduleEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Запись расписания не найдена")
    group = db.get(Group, entry.group_id)
    _can_manage(db, user, group)
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/{group_id}/create-sessions", response_model=CreateSessionsResult)
def create_sessions(
    group_id: int,
    data: CreateSessionsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group = _get_group(db, group_id)
    _can_manage(db, user, group)
    if user.role == UserRole.monitor and data.date != date.today():
        raise HTTPException(
            status_code=403, detail="Староста может создавать рапортички только за текущий день"
        )
    day_num = data.date.isoweekday()
    entries = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.group_id == group_id,
            ScheduleEntry.day_of_week == day_num,
            ScheduleEntry.cancelled.is_(False),
        )
        .order_by(ScheduleEntry.pair_number)
        .all()
    )
    existing = {
        s.pair_number: s
        for s in db.query(AttendanceSession).filter(
            AttendanceSession.group_id == group_id,
            AttendanceSession.date == data.date,
        ).all()
    }

    created = []
    skipped = []

    if data.mode == "resync":
        template_pairs = {e.pair_number for e in entries}
        for s in list(existing.values()):
            if s.pair_number not in template_pairs:
                if s.confirmed:
                    skipped.append({
                        "pair_number": s.pair_number,
                        "reason": "подтверждена преподавателем — не удалена",
                    })
                    continue
                db.delete(s)
                existing.pop(s.pair_number, None)

    for entry in entries:
        if entry.pair_number in existing:
            skipped.append({
                "pair_number": entry.pair_number,
                "subject_name": entry.subject.name if entry.subject else None,
                "reason": "уже существует",
            })
            continue
        session = AttendanceSession(
            group_id=group_id,
            subject_id=entry.subject_id,
            date=data.date,
            pair_number=entry.pair_number,
            created_by=user.id,
        )
        db.add(session)
        db.flush()
        for st in group.students:
            db.add(AttendanceRecord(session_id=session.id, student_id=st.id, mark=MarkValue.present))
        created.append(session.id)
    db.commit()

    return CreateSessionsResult(
        group_id=group_id,
        date=data.date,
        created=created,
        skipped=skipped,
        created_count=len(created),
        skipped_count=len(skipped),
    )
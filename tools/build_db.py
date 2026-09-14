"""Сборка базы данных для развёртывания.

Повторяет вызовы API `/schedule/{group_id}/source`, `/schedule/{group_id}/import`
и `/schedule/{group_id}/create-sessions` для демо-группы (id=1, ТЕСТ.00.00.1)
напрямую через сервисы backend. Запускать из каталога backend:

    DATABASE_URL='postgresql://...' python tools/build_db.py
"""

import sys
from datetime import date

from database import SessionLocal
from models import AttendanceRecord, AttendanceSession, Group, MarkValue, ScheduleEntry, Subject, User, UserRole
from services import ktc
from services.schedule_import import match_subject_by_name, match_teacher_by_surname

BRANCH_ID = 1  # отделение КТК, которому принадлежит ТЕСТ.00.00.1
KTC_GROUP_ID = 297  # группа "ТЕСТ.00.00.1" в КТК


def import_schedule(db):
    group = db.get(Group, 1)
    if group is None:
        sys.exit("Группа id=1 не найдена (запустите seed.py)")
    group.ktc_branch_id = BRANCH_ID
    group.ktc_group_id = KTC_GROUP_ID

    week_data = ktc.fetch_timetable(KTC_GROUP_ID)
    subjects = db.query(Subject).all()
    teachers = db.query(User).filter(User.role == UserRole.teacher).all()
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

            name = (lesson.get("title") or "").strip()
            subject = match_subject_by_name(name, subjects) if name else None
            if subject is None and name:
                subject = Subject(name=name)
                db.add(subject)
                db.flush()
                subjects.append(subject)
                subjects_created.append(name)

            short_teacher = (lesson.get("teacher") or "").strip()
            teacher = match_teacher_by_surname(short_teacher, teachers) if short_teacher else None
            if teacher:
                teachers_matched.append(short_teacher)
                if subject is not None and subject.teacher_id is None:
                    subject.teacher_id = teacher.id

            classroom = (lesson.get("actual_classroom") or lesson.get("classroom") or "").strip()
            cancelled = bool(lesson.get("cancelled")) or lesson.get("status") == 1

            entry = (
                db.query(ScheduleEntry)
                .filter(
                    ScheduleEntry.group_id == group.id,
                    ScheduleEntry.day_of_week == day_num,
                    ScheduleEntry.pair_number == pair,
                )
                .first()
            )
            time_start = t[1] if len(t) >= 2 else None
            time_end = t[2] if len(t) >= 3 else None
            if entry:
                entry.subject_id = subject.id if subject else None
                entry.teacher_id = teacher.id if teacher else None
                entry.teacher_name = short_teacher or None
                entry.classroom = classroom or None
                entry.time_start = time_start
                entry.time_end = time_end
                entry.cancelled = cancelled
            else:
                db.add(ScheduleEntry(
                    group_id=group.id,
                    day_of_week=day_num,
                    pair_number=pair,
                    subject_id=subject.id if subject else None,
                    teacher_id=teacher.id if teacher else None,
                    teacher_name=short_teacher or None,
                    classroom=classroom or None,
                    time_start=time_start,
                    time_end=time_end,
                    cancelled=cancelled,
                ))
    db.commit()
    return {"entries": len(fetched_keys), "subjects_created": subjects_created,
            "teachers_matched": teachers_matched}


def create_sessions(db):
    group = db.get(Group, 1)
    today = date.today()
    day_num = today.isoweekday()
    entries = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.group_id == group.id,
            ScheduleEntry.day_of_week == day_num,
            ScheduleEntry.cancelled.is_(False),
        )
        .order_by(ScheduleEntry.pair_number)
        .all()
    )
    existing = {
        s.pair_number: s
        for s in db.query(AttendanceSession).filter(
            AttendanceSession.group_id == group.id,
            AttendanceSession.date == today,
        ).all()
    }
    created = []
    for entry in entries:
        if entry.pair_number in existing:
            continue
        session = AttendanceSession(
            group_id=group.id,
            subject_id=entry.subject_id,
            date=today,
            pair_number=entry.pair_number,
        )
        db.add(session)
        db.flush()
        for st in group.students:
            db.add(AttendanceRecord(session_id=session.id, student_id=st.id, mark=MarkValue.present))
        created.append(session.id)
    db.commit()
    return {"sessions": created}


if __name__ == "__main__":
    db = SessionLocal()
    try:
        print("Импорт расписания КТК:", import_schedule(db))
        print("Сессии на сегодня:", create_sessions(db))
    finally:
        db.close()
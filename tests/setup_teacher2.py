import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    AttendanceRecord,
    AttendanceSession,
    Group,
    MarkValue,
    Subject,
    User,
    UserRole,
)

db = SessionLocal()

tea2 = db.query(User).filter(User.login == "teacher2").first()
if not tea2:
    tea2 = User(
        login="teacher2",
        password_hash=hash_password("teacher2"),
        full_name="Демо Преподаватель Демоевич",
        role=UserRole.teacher,
    )
    db.add(tea2)
    db.flush()
    print("created teacher2 id", tea2.id)
else:
    print("teacher2 exists id", tea2.id)

phys = db.query(Subject).filter(Subject.name == "Физика").first()
math = db.query(Subject).filter(Subject.name == "Математика").first()
print("phys", phys.id if phys else None, "math", math.id if math else None)

phys.teacher_id = tea2.id
if math is not None:
    math.teacher_id = None

group = db.query(Group).order_by(Group.id).first()
print("group", group.id if group else None)

existing = (
    db.query(AttendanceSession)
    .filter(
        AttendanceSession.group_id == group.id,
        AttendanceSession.date == date.today(),
        AttendanceSession.pair_number == 3,
    )
    .first()
)
if not existing and phys is not None:
    s = AttendanceSession(
        group_id=group.id, subject_id=phys.id, date=date.today(), pair_number=3
    )
    db.add(s)
    db.flush()
    for st in group.students:
        db.add(AttendanceRecord(session_id=s.id, student_id=st.id, mark=MarkValue.present))
    print("created subject-teacher session (pair 3, Физика)")

db.commit()
db.close()
print("setup done")
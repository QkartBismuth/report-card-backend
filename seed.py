import sys
from pathlib import Path

from sqlalchemy.orm import Session

import models  # noqa: F401
from auth import hash_password
from database import Base, SessionLocal, engine
from models import Group, Student, Subject, User, UserRole
from services.docx_parser import parse_raport

SAMPLE_STUDENTS = [
    "Демо Студент 01",
    "Демо Студент 02",
    "Демо Студент 03",
    "Демо Студент 04",
    "Демо Студент 05",
    "Демо Студент 06",
    "Демо Студент 07",
    "Демо Студент 08",
    "Демо Студент 09",
    "Демо Студент 10",
    "Демо Студент 11",
    "Демо Студент 12",
]

SUBJECTS = [
    "Программирование",
    "Базы данных",
    "Математика",
    "Физика",
    "Английский язык",
    "Информационные технологии",
]


def seed(raport_path: str | None = None):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()

    teacher = User(
        login="teacher",
        password_hash=hash_password("teacher123"),
        full_name="Преподаватель Демо",
        role=UserRole.teacher,
    )
    monitor = User(
        login="starosta",
        password_hash=hash_password("starosta123"),
        full_name="Староста Демо",
        role=UserRole.monitor,
    )
    admin = User(
        login="admin",
        password_hash=hash_password("admin123"),
        full_name="Администратор системы",
        role=UserRole.admin,
    )
    db.add_all([teacher, monitor, admin])
    db.flush()

    if raport_path and Path(raport_path).is_file():
        with open(raport_path, "rb") as f:
            result = parse_raport(f.read())
        group_name, group_year, students = (
            result["group_name"],
            result["group_year"],
            result["students"],
        )
    else:
        group_name, group_year, students = "ТЕСТ.00.00.1", 2026, SAMPLE_STUDENTS
        if raport_path and not Path(raport_path).is_file():
            print(f"ВНИМАНИЕ: файл рапортички '{raport_path}' не найден, "
                  "используется демо-группа.")

    group = Group(name=group_name, year=group_year, curator_id=teacher.id)
    db.add(group)
    db.flush()

    monitor.group_id = group.id

    for name in students:
        db.add(Student(group_id=group.id, full_name=name))

    for subj_name in SUBJECTS:
        db.add(Subject(name=subj_name, teacher_id=teacher.id))

    db.commit()
    db.close()

    print(f"Группа: {group_name} ({group_year})")
    print(f"Студентов: {len(students)}")
    print("Пользователи: teacher/teacher123, starosta/starosta123, admin/admin123")


if __name__ == "__main__":
    sys.path.insert(0, ".")  # support import when run as script
    seed(sys.argv[1] if len(sys.argv) > 1 else None)
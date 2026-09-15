import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    teacher = "teacher"
    monitor = "monitor"
    admin = "admin"
    department_head = "department_head"


class MarkValue(str, enum.Enum):
    late = "late"
    absent = "absent"
    excused = "excused"
    present = "present"
    o = "o"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(Enum(UserRole, name="user_role"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", name="fk_users_group"), nullable=True)

    group = relationship("Group", foreign_keys=[group_id])


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    teacher = relationship("User", foreign_keys=[teacher_id])
    sessions = relationship("AttendanceSession", back_populates="subject")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    year = Column(Integer, nullable=True)
    curator_id = Column(Integer, ForeignKey("users.id", name="fk_groups_curator"), nullable=True)
    department_head_id = Column(
        Integer, ForeignKey("users.id", name="fk_groups_department_head"), nullable=True
    )
    ktc_branch_id = Column(Integer, nullable=True)
    ktc_group_id = Column(Integer, nullable=True)

    curator = relationship("User", foreign_keys=[curator_id])
    department_head = relationship("User", foreign_keys=[department_head_id])
    students = relationship("Student", back_populates="group", cascade="all, delete-orphan")
    sessions = relationship("AttendanceSession", back_populates="group")
    schedule = relationship("ScheduleEntry", back_populates="group", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(150), nullable=False)

    group = relationship("Group", back_populates="students")
    records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    date = Column(Date, nullable=False)
    pair_number = Column(Integer, nullable=False)
    confirmed = Column(Boolean, default=False, nullable=False)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("Group", back_populates="sessions")
    subject = relationship("Subject", back_populates="sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    mark = Column(
        Enum(MarkValue, name="mark_value"), default=MarkValue.present, nullable=False
    )
    comment = Column(Text, nullable=True)

    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="records")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(200), unique=True, nullable=False, index=True)
    platform = Column(String(50), nullable=True)
    model = Column(String(200), nullable=True)
    manufacturer = Column(String(200), nullable=True)
    os_version = Column(String(100), nullable=True)
    app_version = Column(String(50), nullable=True)
    ip = Column(String(64), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(200), nullable=True)
    app_version = Column(String(50), nullable=True)
    message = Column(Text, nullable=False)
    stack = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    pair_number = Column(Integer, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    teacher_name = Column(String(150), nullable=True)
    classroom = Column(String(50), nullable=True)
    time_start = Column(String(10), nullable=True)
    time_end = Column(String(10), nullable=True)
    cancelled = Column(Boolean, default=False, nullable=False)
    note = Column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "group_id", "day_of_week", "pair_number", name="uq_schedule_group_day_pair"
        ),
    )

    group = relationship("Group", back_populates="schedule")
    subject = relationship("Subject")
    teacher = relationship("User", foreign_keys=[teacher_id])


class ServerConfig(Base):
    __tablename__ = "server_config"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)


def get_config(db, key: str, default=None):
    row = db.query(ServerConfig).filter(ServerConfig.key == key).first()
    return row.value if row else default


def set_config(db, key: str, value):
    row = db.query(ServerConfig).filter(ServerConfig.key == key).first()
    if row:
        row.value = value
    else:
        db.add(ServerConfig(key=key, value=value))
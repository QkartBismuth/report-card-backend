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
    func,
)
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    teacher = "teacher"
    monitor = "monitor"


class MarkValue(str, enum.Enum):
    late = "late"
    absent = "absent"
    excused = "excused"
    present = "present"


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

    curator = relationship("User", foreign_keys=[curator_id])
    students = relationship("Student", back_populates="group", cascade="all, delete-orphan")
    sessions = relationship("AttendanceSession", back_populates="group")


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

    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="records")
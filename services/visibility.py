from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AttendanceSession, Group, Subject, User, UserRole


def visible_groups(db: Session, user: User) -> list[Group]:
    """Группы, которые видит пользователь."""
    q = db.query(Group)
    if user.role == UserRole.admin:
        return q.order_by(Group.name).all()
    if user.role == UserRole.monitor:
        if user.group_id is None:
            return []
        return q.filter(Group.id == user.group_id).order_by(Group.name).all()
    if user.role == UserRole.department_head:
        return (
            q.filter(Group.department_head_id == user.id)
            .order_by(Group.name)
            .all()
        )
    taught_ids = (
        select(AttendanceSession.group_id)
        .join(Subject, AttendanceSession.subject_id == Subject.id)
        .where(Subject.teacher_id == user.id)
        .distinct()
    )
    return (
        q.filter(
            (Group.curator_id == user.id) | (Group.id.in_(taught_ids))
        )
        .order_by(Group.name)
        .all()
    )


def can_access_session(db: Session, user: User, s: AttendanceSession) -> bool:
    """Может ли пользователь видеть/подтверждать сессию."""
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.monitor:
        return user.group_id is not None and s.group_id == user.group_id
    if user.role == UserRole.department_head:
        return s.group is not None and s.group.department_head_id == user.id
    if s.group is not None and s.group.curator_id == user.id:
        return True
    if s.subject is not None and s.subject.teacher_id == user.id:
        return True
    return False
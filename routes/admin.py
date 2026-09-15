from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password, require_admin
from database import get_db
from models import (
    AttendanceSession,
    Device,
    ErrorLog,
    Group,
    Student,
    Subject,
    User,
    UserRole,
    get_config,
    set_config,
)
from schemas import (
    DepartmentHeadCreate,
    DepartmentHeadOut,
    DepartmentHeadUpdate,
    DeviceOut,
    ErrorOut,
    GroupCreate,
    GroupUpdate,
    MonitorCreate,
    MonitorOut,
    MonitorUpdate,
    PushConfigOut,
    ServerConfigOut,
    ServerConfigUpdate,
    TeacherCreate,
    TeacherOut,
    TeacherUpdate,
    TunnelStartRequest,
    TunnelStatusOut,
)
from services.tunnel import tunnel as tunnel_manager

router = APIRouter(prefix="/admin", tags=["admin"])


def _config_version(db) -> int:
    raw = get_config(db, "config_version", "1")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _config_db(db) -> ServerConfigOut:
    return ServerConfigOut(
        server_url=get_config(db, "server_url"),
        wifi_ssid=get_config(db, "wifi_ssid"),
        wifi_password=get_config(db, "wifi_password"),
    )


def _bump_config(db):
    set_config(db, "config_version", str(_config_version(db) + 1))
    db.commit()


# --------------- Teachers ---------------

@router.get("/teachers", response_model=list[TeacherOut])
def list_teachers(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return (
        db.query(User)
        .filter(User.role == UserRole.teacher)
        .order_by(User.full_name)
        .all()
    )


@router.post("/teachers", response_model=TeacherOut, status_code=201)
def create_teacher(
    data: TeacherCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    login = data.login.strip()
    if not login or not data.password:
        raise HTTPException(status_code=422, detail="Логин и пароль обязательны")
    if db.query(User).filter(User.login == login).first():
        raise HTTPException(status_code=409, detail="Логин уже занят")
    if not data.full_name.strip():
        raise HTTPException(status_code=422, detail="ФИО не может быть пустым")
    teacher = User(
        login=login,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        role=UserRole.teacher,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.patch("/teachers/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    t = db.get(User, teacher_id)
    if not t or t.role != UserRole.teacher:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")
    if data.login is not None:
        login = data.login.strip()
        if not login:
            raise HTTPException(status_code=422, detail="Логин не может быть пустым")
        if db.query(User).filter(User.login == login, User.id != t.id).first():
            raise HTTPException(status_code=409, detail="Логин уже занят")
        t.login = login
    if data.full_name is not None:
        if not data.full_name.strip():
            raise HTTPException(status_code=422, detail="ФИО не может быть пустым")
        t.full_name = data.full_name.strip()
    if data.password:
        t.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/teachers/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    t = db.get(User, teacher_id)
    if not t or t.role != UserRole.teacher:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")
    admin_count = db.query(User).filter(User.role == UserRole.admin).count()
    if admin_count <= 1 and t.id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора")
    db.query(Group).filter(Group.curator_id == teacher_id).update({"curator_id": None})
    db.query(Subject).filter(Subject.teacher_id == teacher_id).update({"teacher_id": None})
    db.query(AttendanceSession).filter(AttendanceSession.created_by == teacher_id).update(
        {"created_by": None}
    )
    db.query(AttendanceSession).filter(
        AttendanceSession.confirmed_by == teacher_id
    ).update({"confirmed_by": None})
    db.query(Device).filter(Device.user_id == teacher_id).update({"user_id": None})
    db.delete(t)
    db.commit()
    return {"ok": True}


# --------------- Groups / curators ---------------

@router.post("/groups", response_model=dict, status_code=201)
def create_group(
    data: GroupCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название группы пустое")
    if db.query(Group).filter(Group.name == name).first():
        raise HTTPException(status_code=409, detail="Группа с таким названием уже есть")
    g = Group(name=name, year=data.year)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {
        "id": g.id,
        "name": g.name,
        "year": g.year,
        "curator_id": g.curator_id,
        "curator_name": g.curator.full_name if g.curator else None,
        "department_head_id": g.department_head_id,
        "department_head_name": g.department_head.full_name if g.department_head else None,
    }


@router.patch("/groups/{group_id}", response_model=dict)
def update_group(
    group_id: int,
    data: GroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Название группы пустое")
        if db.query(Group).filter(Group.name == name, Group.id != g.id).first():
            raise HTTPException(status_code=409, detail="Группа с таким названием уже есть")
        g.name = name
    if data.year is not None:
        g.year = data.year
    if "curator_id" in data.model_fields_set:
        if data.curator_id is None:
            g.curator_id = None
        else:
            curator = db.get(User, data.curator_id)
            if not curator or curator.role != UserRole.teacher:
                raise HTTPException(status_code=400, detail="Куратор должен быть преподавателем")
            g.curator_id = data.curator_id
    if "department_head_id" in data.model_fields_set:
        if data.department_head_id is None:
            g.department_head_id = None
        else:
            head = db.get(User, data.department_head_id)
            if not head or head.role != UserRole.department_head:
                raise HTTPException(
                    status_code=400, detail="Завотделением должен быть пользователь с ролью «Завотделения»"
                )
            g.department_head_id = data.department_head_id
    db.commit()
    db.refresh(g)
    return {
        "id": g.id,
        "name": g.name,
        "year": g.year,
        "curator_id": g.curator_id,
        "curator_name": g.curator.full_name if g.curator else None,
        "department_head_id": g.department_head_id,
        "department_head_name": g.department_head.full_name if g.department_head else None,
    }


# --------------- Monitors ---------------

def _monitor_out(u: User) -> dict:
    return {
        "id": u.id,
        "login": u.login,
        "full_name": u.full_name,
        "group_id": u.group_id,
        "group_name": u.group.name if u.group else None,
    }


@router.get("/monitors", response_model=list[MonitorOut])
def list_monitors(
    group_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(User).filter(User.role == UserRole.monitor)
    if group_id is not None:
        q = q.filter(User.group_id == group_id)
    return [_monitor_out(m) for m in q.order_by(User.full_name).all()]


@router.post("/monitors", response_model=MonitorOut, status_code=201)
def create_monitor(
    data: MonitorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    login = data.login.strip()
    if not login or not data.password:
        raise HTTPException(status_code=422, detail="Логин и пароль обязательны")
    if db.query(User).filter(User.login == login).first():
        raise HTTPException(status_code=409, detail="Логин уже занят")
    student = db.get(Student, data.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")
    existing = (
        db.query(User)
        .filter(User.role == UserRole.monitor, User.group_id == student.group_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Староста для этой группы уже назначен. Сначала удалите текущего.",
        )
    monitor = User(
        login=login,
        password_hash=hash_password(data.password),
        full_name=student.full_name,
        role=UserRole.monitor,
        group_id=student.group_id,
    )
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    return _monitor_out(monitor)


@router.patch("/monitors/{monitor_id}", response_model=MonitorOut)
def update_monitor(
    monitor_id: int,
    data: MonitorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    m = db.get(User, monitor_id)
    if not m or m.role != UserRole.monitor:
        raise HTTPException(status_code=404, detail="Староста не найден")
    if data.student_id is not None:
        student = db.get(Student, data.student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Студент не найден")
        m.group_id = student.group_id
        m.full_name = student.full_name
    if data.login is not None:
        login = data.login.strip()
        if not login:
            raise HTTPException(status_code=422, detail="Логин не может быть пустым")
        if db.query(User).filter(User.login == login, User.id != m.id).first():
            raise HTTPException(status_code=409, detail="Логин уже занят")
        m.login = login
    if data.password:
        m.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(m)
    return _monitor_out(m)


@router.delete("/monitors/{monitor_id}")
def delete_monitor(
    monitor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    m = db.get(User, monitor_id)
    if not m or m.role != UserRole.monitor:
        raise HTTPException(status_code=404, detail="Староста не найден")
    db.query(AttendanceSession).filter(AttendanceSession.created_by == monitor_id).update(
        {"created_by": None}
    )
    db.query(AttendanceSession).filter(
        AttendanceSession.confirmed_by == monitor_id
    ).update({"confirmed_by": None})
    db.query(Device).filter(Device.user_id == monitor_id).update({"user_id": None})
    db.delete(m)
    db.commit()
    return {"ok": True}


# --------------- Department heads (завотделения) ---------------

def _head_out(u: User) -> dict:
    return {
        "id": u.id,
        "login": u.login,
        "full_name": u.full_name,
        "role": u.role.value,
    }


@router.get("/department_heads", response_model=list[DepartmentHeadOut])
def list_department_heads(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return (
        db.query(User)
        .filter(User.role == UserRole.department_head)
        .order_by(User.full_name)
        .all()
    )


@router.post("/department_heads", response_model=DepartmentHeadOut, status_code=201)
def create_department_head(
    data: DepartmentHeadCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    login = data.login.strip()
    if not login or not data.password:
        raise HTTPException(status_code=422, detail="Логин и пароль обязательны")
    if db.query(User).filter(User.login == login).first():
        raise HTTPException(status_code=409, detail="Логин уже занят")
    if not data.full_name.strip():
        raise HTTPException(status_code=422, detail="ФИО не может быть пустым")
    head = User(
        login=login,
        password_hash=hash_password(data.password),
        full_name=data.full_name.strip(),
        role=UserRole.department_head,
    )
    db.add(head)
    db.commit()
    db.refresh(head)
    return _head_out(head)


@router.patch("/department_heads/{head_id}", response_model=DepartmentHeadOut)
def update_department_head(
    head_id: int,
    data: DepartmentHeadUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    h = db.get(User, head_id)
    if not h or h.role != UserRole.department_head:
        raise HTTPException(status_code=404, detail="Завотделение не найден")
    if data.login is not None:
        login = data.login.strip()
        if not login:
            raise HTTPException(status_code=422, detail="Логин не может быть пустым")
        if db.query(User).filter(User.login == login, User.id != h.id).first():
            raise HTTPException(status_code=409, detail="Логин уже занят")
        h.login = login
    if data.full_name is not None:
        if not data.full_name.strip():
            raise HTTPException(status_code=422, detail="ФИО не может быть пустым")
        h.full_name = data.full_name.strip()
    if data.password:
        h.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(h)
    return _head_out(h)


@router.delete("/department_heads/{head_id}")
def delete_department_head(
    head_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    h = db.get(User, head_id)
    if not h or h.role != UserRole.department_head:
        raise HTTPException(status_code=404, detail="Завотделение не найден")
    db.query(Group).filter(Group.department_head_id == head_id).update(
        {"department_head_id": None}
    )
    db.query(AttendanceSession).filter(
        AttendanceSession.created_by == head_id
    ).update({"created_by": None})
    db.query(Device).filter(Device.user_id == head_id).update({"user_id": None})
    db.delete(h)
    db.commit()
    return {"ok": True}


# --------------- Analytics: devices / errors ---------------

@router.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Device).order_by(Device.last_seen.desc()).all()


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.delete("/devices")
def clear_devices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    n = db.query(Device).delete()
    db.commit()
    return {"deleted": n}


@router.get("/errors", response_model=list[ErrorOut])
def list_errors(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(ErrorLog).order_by(ErrorLog.created_at.desc()).all()


@router.delete("/errors/{error_id}")
def delete_error(
    error_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    e = db.get(ErrorLog, error_id)
    if not e:
        raise HTTPException(status_code=404, detail="Ошибка не найдена")
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.delete("/errors")
def clear_errors(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    n = db.query(ErrorLog).delete()
    db.commit()
    return {"deleted": n}


# --------------- Connection config ---------------

@router.get("/config", response_model=ServerConfigOut)
def get_server_config(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return _config_db(db)


@router.post("/config", response_model=ServerConfigOut)
def update_server_config(
    data: ServerConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    changes = 0
    if data.server_url is not None:
        url = data.server_url.strip()
        if url and not url.startswith("http"):
            url = "http://" + url
        set_config(db, "server_url", url or None)
        changes += 1
    if data.wifi_ssid is not None:
        set_config(db, "wifi_ssid", data.wifi_ssid.strip() or None)
        changes += 1
    if data.wifi_password is not None:
        set_config(db, "wifi_password", data.wifi_password or None)
        changes += 1
    if changes:
        _bump_config(db)
    return _config_db(db)


# --------------- Tunnel ---------------

@router.get("/tunnel/status", response_model=TunnelStatusOut)
def tunnel_status(_: User = Depends(require_admin)):
    return tunnel_manager.status()


@router.post("/tunnel/start", response_model=TunnelStatusOut)
def tunnel_start(
    data: TunnelStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = tunnel_manager.start(data.provider, data.token)
    if result["url"]:
        set_config(db, "server_url", result["url"])
        _bump_config(db)
    return result


@router.post("/tunnel/stop", response_model=TunnelStatusOut)
def tunnel_stop(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return tunnel_manager.stop()


@router.post("/tunnel/send-url")
def tunnel_send_url(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    status = tunnel_manager.status()
    url = status.get("url")
    if status.get("running") and url:
        set_config(db, "server_url", url)
        _bump_config(db)
        return {"ok": True, "url": url}
    return {"ok": False, "error": "Туннель не запущен или URL ещё не получен"}
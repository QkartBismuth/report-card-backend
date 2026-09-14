from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    login: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    user_id: int
    group_id: Optional[int] = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    year: Optional[int] = None
    curator_id: Optional[int] = None
    curator_name: Optional[str] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_id: int
    full_name: str


class StudentCreate(BaseModel):
    full_name: str


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None


class SubjectCreate(BaseModel):
    name: str


class SubjectUpdate(BaseModel):
    teacher_id: Optional[int] = None


class SessionCreate(BaseModel):
    group_id: int
    date: date
    pair_number: int
    subject_id: Optional[int] = None


class SessionUpdate(BaseModel):
    subject_id: Optional[int] = None
    date: Optional[date] = None
    pair_number: Optional[int] = None


class RecordUpdate(BaseModel):
    records: List[dict]


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    student_id: int
    mark: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_id: int
    group_name: Optional[str] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    date: date
    pair_number: int
    confirmed: bool
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class SessionDetail(SessionOut):
    records: List[RecordOut] = []


class UploadRaportResponse(BaseModel):
    group_name: str
    group_year: Optional[int] = None
    students: List[str] = []
    parsed_at: str


class ApplyRaportRequest(BaseModel):
    group_name: str
    group_year: Optional[int] = None
    students: List[str]


class ConfirmResponse(BaseModel):
    session_id: int
    confirmed: bool
    confirmed_at: Optional[datetime] = None


# --------------- Admin / analytics / config ---------------

class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    login: str
    full_name: str
    role: str


class TeacherCreate(BaseModel):
    login: str
    full_name: str
    password: str


class TeacherUpdate(BaseModel):
    full_name: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None


class GroupCreate(BaseModel):
    name: str
    year: Optional[int] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    year: Optional[int] = None
    curator_id: Optional[int] = None
    teacher_id: Optional[int] = None  # deprecated, keep for compat


class StudentUpdate(BaseModel):
    full_name: str


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str
    platform: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    ip: Optional[str] = None
    user_id: Optional[int] = None
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    message: str
    stack: Optional[str] = None
    created_at: Optional[datetime] = None


class DeviceRegister(BaseModel):
    device_id: str
    platform: str = "android"
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    user_id: Optional[int] = None


class ErrorCreate(BaseModel):
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    message: str
    stack: Optional[str] = None


class ServerConfigOut(BaseModel):
    server_url: Optional[str] = None
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None


class ServerConfigUpdate(BaseModel):
    server_url: Optional[str] = None
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None


class PushConfigOut(BaseModel):
    version: int
    server_url: Optional[str] = None
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None


class TunnelStartRequest(BaseModel):
    provider: str
    token: Optional[str] = None


class TunnelStatusOut(BaseModel):
    running: bool
    provider: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


# --------------- KTK / Расписание ---------------

class KtcGroupOut(BaseModel):
    id: int
    title: str


class KtcCourseOut(BaseModel):
    course: int
    groups: List[KtcGroupOut]


class KtcBranchOut(BaseModel):
    id: int
    title: str


class KtcTeacherOut(BaseModel):
    id: int
    name: str


class ScheduleSourceSet(BaseModel):
    ktc_branch_id: Optional[int] = None
    ktc_group_id: Optional[int] = None


class ScheduleImportRequest(BaseModel):
    week: Optional[int] = None
    replace: bool = False


class ScheduleEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_id: int
    day_of_week: int
    pair_number: int
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    teacher_full_name: Optional[str] = None
    classroom: Optional[str] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    cancelled: bool
    note: Optional[str] = None


class ScheduleEntryCreate(BaseModel):
    day_of_week: int
    pair_number: int
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    classroom: Optional[str] = None
    cancelled: bool = False
    note: Optional[str] = None


class ScheduleEntryUpdate(BaseModel):
    day_of_week: Optional[int] = None
    pair_number: Optional[int] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    classroom: Optional[str] = None
    cancelled: Optional[bool] = None
    note: Optional[str] = None


class CreateSessionsRequest(BaseModel):
    date: date
    mode: str = "missing"


class CreateSessionsResult(BaseModel):
    group_id: int
    date: date
    created: List[int]
    skipped: List[dict]
    created_count: int
    skipped_count: int


class ScheduleImportResult(BaseModel):
    group_id: int
    week: Optional[int]
    entries_count: int
    subjects_created: List[str]
    teachers_matched: List[str]
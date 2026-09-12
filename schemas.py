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
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_db
from models import User
from schemas import KtcBranchOut, KtcCourseOut, KtcTeacherOut
from services import ktc
from sqlalchemy.orm import Session

router = APIRouter(prefix="/ktc", tags=["ktc"])


def _ktc_or_400(fn):
    try:
        return fn()
    except ktc.KtcError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/branches", response_model=list[KtcBranchOut])
def branches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _ktc_or_400(ktc.fetch_branches)


@router.get("/courses/{branch_id}", response_model=list[KtcCourseOut])
def courses(branch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _ktc_or_400(lambda: ktc.fetch_courses(branch_id))


@router.get("/teachers/{branch_id}", response_model=list[KtcTeacherOut])
def teachers(branch_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _ktc_or_400(lambda: ktc.fetch_teachers(branch_id))
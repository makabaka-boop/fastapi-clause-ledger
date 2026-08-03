from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..constants import RISK_LEVELS
from ..database import get_db
from ..exceptions import ValidationError
from ..schemas import ProcessRecordCreate, ProcessRecordOut, ReviewOut, ReviewStatusChange
from ..services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=List[ReviewOut])
def list_open_reviews_by_risk(
    risk_level: str = Query(..., description="风险等级"),
    db: Session = Depends(get_db),
):
    """按风险等级查询未处理（open）意见。"""
    if risk_level not in RISK_LEVELS:
        raise ValidationError(
            f"risk_level 必须是 {list(RISK_LEVELS)} 之一", {"risk_level": risk_level}
        )
    return ReviewService(db).list_open_by_risk_level(risk_level)


@router.post("/{review_id}/status", response_model=ReviewOut)
def change_review_status(review_id: int, data: ReviewStatusChange, db: Session = Depends(get_db)):
    return ReviewService(db).change_status(review_id, data)


@router.post("/{review_id}/records", response_model=ProcessRecordOut, status_code=201)
def write_process_record(review_id: int, data: ProcessRecordCreate, db: Session = Depends(get_db)):
    return ReviewService(db).write_process_record(review_id, data)


@router.get("/{review_id}/records", response_model=List[ProcessRecordOut])
def list_process_history(review_id: int, db: Session = Depends(get_db)):
    return ReviewService(db).list_history(review_id)

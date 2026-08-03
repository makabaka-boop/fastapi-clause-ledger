from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ClauseOut, ReviewCreate, ReviewOut, TagBindingCreate, TagBindingOut
from ..services.clause_service import ClauseService
from ..services.review_service import ReviewService
from ..services.tag_service import TagService

router = APIRouter(prefix="/clauses", tags=["clauses"])


@router.post("/{clause_id}/deprecate", response_model=ClauseOut)
def deprecate_clause(clause_id: int, db: Session = Depends(get_db)):
    return ClauseService(db).deprecate(clause_id)


@router.post("/{clause_id}/reviews", response_model=ReviewOut, status_code=201)
def add_review(clause_id: int, data: ReviewCreate, db: Session = Depends(get_db)):
    return ReviewService(db).add_review(clause_id, data)


@router.get("/{clause_id}/reviews", response_model=List[ReviewOut])
def list_clause_reviews(clause_id: int, db: Session = Depends(get_db)):
    """条款历史意见（含已废弃条款）。"""
    return ReviewService(db).list_by_clause(clause_id)


@router.post("/{clause_id}/tags", response_model=TagBindingOut, status_code=201)
def bind_tag(clause_id: int, data: TagBindingCreate, db: Session = Depends(get_db)):
    return TagService(db).bind_tag(clause_id, data.tag_id)

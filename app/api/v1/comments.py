from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_comment_service
from app.enums import RiskLevel
from app.schemas.comment import (
    ClauseWithLatestComment,
    CommentCreate,
    CommentOut,
    CommentStatusUpdate,
)
from app.services.comment_service import CommentService

router = APIRouter(tags=["comments"])


@router.post(
    "/clauses/{clause_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    clause_id: int,
    payload: CommentCreate,
    service: CommentService = Depends(get_comment_service),
):
    return service.add_comment(clause_id, payload)


@router.get(
    "/documents/{document_id}/clauses/latest-comments",
    response_model=List[ClauseWithLatestComment],
)
def list_clauses_with_latest_comments(
    document_id: int,
    service: CommentService = Depends(get_comment_service),
):
    return service.list_clauses_with_latest_comments(document_id)


@router.get(
    "/comments/unresolved",
    response_model=List[CommentOut],
)
def list_unresolved_by_risk(
    risk_level: RiskLevel = Query(...),
    document_id: Optional[int] = Query(None),
    service: CommentService = Depends(get_comment_service),
):
    return service.list_unresolved_by_risk(risk_level, document_id)


@router.get("/comments/{comment_id}", response_model=CommentOut)
def get_comment(
    comment_id: int,
    service: CommentService = Depends(get_comment_service),
):
    return service.get_comment(comment_id)


@router.patch("/comments/{comment_id}/status", response_model=CommentOut)
def update_comment_status(
    comment_id: int,
    payload: CommentStatusUpdate,
    service: CommentService = Depends(get_comment_service),
):
    return service.change_status(comment_id, payload)

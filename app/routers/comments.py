from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db
from app.enums import RiskLevel

router = APIRouter(tags=["comments"])


@router.post(
    "/clauses/{clause_id}/comments",
    response_model=schemas.CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    clause_id: int,
    payload: schemas.CommentCreate,
    db: Session = Depends(get_db),
) -> schemas.CommentOut:
    service = services.CommentService(db)
    comment = service.add_comment(payload, clause_id)
    return schemas.CommentOut.model_validate(comment)


@router.patch(
    "/comments/{comment_id}/status",
    response_model=schemas.CommentOut,
)
def change_comment_status(
    comment_id: int,
    payload: schemas.CommentStatusUpdate,
    db: Session = Depends(get_db),
) -> schemas.CommentOut:
    service = services.CommentService(db)
    comment, _record = service.change_status(comment_id, payload)
    return schemas.CommentOut.model_validate(comment)


@router.post(
    "/comments/{comment_id}/processing-records",
    response_model=schemas.ProcessingRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def add_processing_record(
    comment_id: int,
    payload: schemas.ProcessingRecordCreate,
    db: Session = Depends(get_db),
) -> schemas.ProcessingRecordOut:
    service = services.CommentService(db)
    record = service.add_processing_record(comment_id, payload)
    return schemas.ProcessingRecordOut.model_validate(record)


@router.get(
    "/comments/{comment_id}/processing-history",
    response_model=list[schemas.ProcessingRecordOut],
)
def list_processing_history(
    comment_id: int,
    db: Session = Depends(get_db),
) -> list[schemas.ProcessingRecordOut]:
    service = services.CommentService(db)
    records = service.list_processing_history(comment_id)
    return [schemas.ProcessingRecordOut.model_validate(r) for r in records]


@router.get(
    "/comments/unresolved",
    response_model=list[schemas.CommentOut],
)
def list_unresolved_by_risk_level(
    risk_level: RiskLevel = Query(..., description="Filter by risk level"),
    db: Session = Depends(get_db),
) -> list[schemas.CommentOut]:
    service = services.CommentService(db)
    comments = service.list_unresolved_by_risk_level(risk_level)
    return [schemas.CommentOut.model_validate(c) for c in comments]

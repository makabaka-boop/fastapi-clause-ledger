from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

router = APIRouter(tags=["clauses"])


@router.post(
    "/documents/{document_id}/clauses/batch",
    response_model=list[schemas.ClauseOut],
    status_code=status.HTTP_201_CREATED,
)
def batch_create_clauses(
    document_id: int,
    payload: schemas.ClauseBatchCreate,
    db: Session = Depends(get_db),
) -> list[schemas.ClauseOut]:
    service = services.ClauseService(db)
    clauses = service.batch_create(document_id, payload)
    return [schemas.ClauseOut.model_validate(c) for c in clauses]


@router.post(
    "/documents/{document_id}/clauses/import",
    response_model=schemas.ClauseImportResult,
)
def import_clauses(
    document_id: int,
    payload: schemas.ClauseImportRequest,
    db: Session = Depends(get_db),
) -> schemas.ClauseImportResult:
    service = services.ClauseService(db)
    clauses, created, updated, skipped, id_mapping = service.idempotent_import(document_id, payload)
    return schemas.ClauseImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        clauses=[schemas.ClauseOut.model_validate(c) for c in clauses],
        id_mapping=[schemas.ClauseIdMapping(**m) for m in id_mapping],
    )


@router.get(
    "/documents/{document_id}/clauses",
    response_model=list[schemas.ClauseWithLatestComment],
)
def list_clauses_by_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[schemas.ClauseWithLatestComment]:
    service = services.ClauseService(db)
    pairs = service.list_by_document_with_latest_comments(document_id)
    response: list[schemas.ClauseWithLatestComment] = []
    for clause, latest_comment in pairs:
        item = schemas.ClauseWithLatestComment.model_validate(clause)
        if latest_comment is not None:
            item.latest_comment = schemas.CommentOut.model_validate(latest_comment)
        response.append(item)
    return response


@router.post(
    "/clauses/{clause_id}/deprecate",
    response_model=schemas.ClauseOut,
)
def deprecate_clause(
    clause_id: int,
    db: Session = Depends(get_db),
) -> schemas.ClauseOut:
    service = services.ClauseService(db)
    clause = service.deprecate(clause_id)
    return schemas.ClauseOut.model_validate(clause)

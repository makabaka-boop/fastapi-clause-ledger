from typing import List

from fastapi import APIRouter, Depends, status

from app.api.deps import get_clause_service
from app.schemas.clause import (
    ClauseBatchCreate,
    ClauseBatchResult,
    ClauseDeprecateOut,
    ClauseImportRequest,
    ClauseImportResult,
    ClauseOut,
)
from app.services.clause_service import ClauseService

router = APIRouter(prefix="/documents/{document_id}/clauses", tags=["clauses"])


@router.post(
    "/batch",
    response_model=ClauseBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def batch_create_clauses(
    document_id: int,
    payload: ClauseBatchCreate,
    service: ClauseService = Depends(get_clause_service),
):
    return service.batch_create(document_id, payload)


@router.post(
    "/import",
    response_model=ClauseImportResult,
    status_code=status.HTTP_201_CREATED,
)
def idempotent_import_clauses(
    document_id: int,
    payload: ClauseImportRequest,
    service: ClauseService = Depends(get_clause_service),
):
    return service.idempotent_import(document_id, payload)


@router.get("", response_model=List[ClauseOut])
def list_clauses(
    document_id: int,
    service: ClauseService = Depends(get_clause_service),
):
    return service.list_by_document(document_id)


@router.post(
    "/{clause_id}/deprecate",
    response_model=ClauseDeprecateOut,
)
def deprecate_clause(
    document_id: int,
    clause_id: int,
    service: ClauseService = Depends(get_clause_service),
):
    return service.deprecate(document_id, clause_id)

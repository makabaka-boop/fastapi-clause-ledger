from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    ClauseBatchCreate,
    ClauseImport,
    ClauseImportResult,
    ClauseOut,
    ClauseWithLatestReview,
    CopyDetailsOut,
    CopyResultOut,
    DocumentCopyCreate,
    DocumentCreate,
    DocumentOut,
    DocumentRiskDashboard,
    DocumentStatusUpdate,
)
from ..services.clause_service import ClauseService
from ..services.copy_service import CopyService
from ..services.dashboard_service import DashboardService
from ..services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=201)
def create_document(data: DocumentCreate, db: Session = Depends(get_db)):
    return DocumentService(db).create_document(data)


@router.get("", response_model=List[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    from ..repositories.documents import DocumentRepository

    return DocumentRepository(db).list_all()


@router.patch("/{document_id}/status", response_model=DocumentOut)
def update_document_status(document_id: int, data: DocumentStatusUpdate, db: Session = Depends(get_db)):
    return DocumentService(db).update_status(document_id, data.document_status)


@router.post("/{document_id}/clauses/batch", response_model=List[ClauseOut], status_code=201)
def batch_create_clauses(document_id: int, data: ClauseBatchCreate, db: Session = Depends(get_db)):
    return ClauseService(db).batch_create(document_id, data)


@router.post("/{document_id}/clauses/import", response_model=ClauseImportResult)
def import_clauses(document_id: int, data: ClauseImport, db: Session = Depends(get_db)):
    result = ClauseService(db).import_clauses(document_id, data)
    return ClauseImportResult(
        mode=result["mode"],
        created_count=len(result["created"]),
        updated_count=len(result["updated"]),
        skipped_count=len(result["skipped"]),
        created=[ClauseOut.model_validate(c) for c in result["created"]],
        updated=[ClauseOut.model_validate(c) for c in result["updated"]],
        skipped=[ClauseOut.model_validate(c) for c in result["skipped"]],
        clause_id_mapping=result["clause_id_mapping"],
    )


@router.get("/{document_id}/clauses", response_model=List[ClauseWithLatestReview])
def list_document_clauses(document_id: int, db: Session = Depends(get_db)):
    return DashboardService(db).clauses_with_latest_review(document_id)


@router.post("/{document_id}/copy", response_model=CopyResultOut, status_code=201)
def copy_document(document_id: int, data: DocumentCopyCreate, db: Session = Depends(get_db)):
    return CopyService(db).copy_document(document_id, data)


@router.get("/{document_id}/copy_details", response_model=CopyDetailsOut)
def copy_details(document_id: int, db: Session = Depends(get_db)):
    """复制结果详情：按目标文档查看每个新条款的原条款、继承标签与未复制原因。"""
    return CopyService(db).copy_details(document_id)


@router.get("/{document_id}/risk_dashboard", response_model=DocumentRiskDashboard)
def risk_dashboard(
    document_id: int,
    include_deprecated: bool = Query(default=False, description="是否包含已废弃条款"),
    db: Session = Depends(get_db),
):
    return DashboardService(db).risk_dashboard(document_id, include_deprecated)

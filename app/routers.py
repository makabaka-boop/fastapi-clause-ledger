"""API routers grouped by resource.

All routes are mounted under ``/api/v1`` by :mod:`app.main`. Routers stay thin:
they translate HTTP <-> schemas and delegate every rule to :mod:`app.services`.
"""

from fastapi import APIRouter, status

from . import services
from .enums import RiskLevel
from .schemas import (
    ClauseBatchCreate,
    ClauseImport,
    ClauseImportResult,
    ClauseOut,
    ClauseTagOut,
    ClauseWithLatestReview,
    ConsistencyReport,
    DocumentCopyDetail,
    DocumentCopyOut,
    DocumentCopyRequest,
    DocumentCopyResult,
    DocumentCreate,
    DocumentOut,
    DocumentStatusUpdate,
    ProcessRecordCreate,
    ProcessRecordOut,
    ReviewCreate,
    ReviewOut,
    ReviewStatusUpdate,
    RiskBoard,
    RiskDashboard,
    RiskTagCreate,
    RiskTagOut,
    TagBindRequest,
    TagRiskDistribution,
)

# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
documents_router = APIRouter(prefix="/documents", tags=["documents"])


@documents_router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate):
    return services.create_document(payload)


@documents_router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int):
    return services.get_document(document_id)


@documents_router.patch("/{document_id}/status", response_model=DocumentOut)
def update_document_status(document_id: int, payload: DocumentStatusUpdate):
    return services.update_document_status(document_id, payload)


@documents_router.post(
    "/{document_id}/clauses",
    response_model=list[ClauseOut],
    status_code=status.HTTP_201_CREATED,
)
def add_clauses(document_id: int, payload: ClauseBatchCreate):
    return services.add_clauses(document_id, payload)


@documents_router.post(
    "/{document_id}/clauses/import", response_model=ClauseImportResult
)
def import_clauses(document_id: int, payload: ClauseImport):
    return services.import_clauses(document_id, payload)


@documents_router.get(
    "/{document_id}/clauses", response_model=list[ClauseWithLatestReview]
)
def list_clauses_with_latest_review(document_id: int):
    return services.list_clauses_with_latest_review(document_id)


@documents_router.get("/{document_id}/dashboard", response_model=RiskDashboard)
def risk_dashboard(document_id: int):
    return services.risk_dashboard(document_id)


@documents_router.get("/{document_id}/risk-board", response_model=RiskBoard)
def risk_board(document_id: int, include_deprecated: bool = False):
    return services.risk_board(document_id, include_deprecated=include_deprecated)


@documents_router.post(
    "/{document_id}/copies",
    response_model=DocumentCopyResult,
    status_code=status.HTTP_201_CREATED,
)
def copy_document(document_id: int, payload: DocumentCopyRequest):
    return services.copy_document(document_id, payload)


@documents_router.get(
    "/{document_id}/copies", response_model=list[DocumentCopyOut]
)
def get_copy_mappings(document_id: int):
    return services.get_copy_mappings(document_id)


@documents_router.get(
    "/{document_id}/copy-detail", response_model=DocumentCopyDetail
)
def get_copy_detail(document_id: int):
    """View how a copied (target) document was built: per new clause, its origin
    clause, inherited risk tags and a summary of what was not copied."""
    return services.get_copy_detail(document_id)


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
clauses_router = APIRouter(prefix="/clauses", tags=["clauses"])


@clauses_router.post("/{clause_id}/deprecate", response_model=ClauseOut)
def deprecate_clause(clause_id: int):
    return services.deprecate_clause(clause_id)


@clauses_router.post(
    "/{clause_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def add_review(clause_id: int, payload: ReviewCreate):
    return services.add_review(clause_id, payload)


@clauses_router.post(
    "/{clause_id}/tags",
    response_model=ClauseTagOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_tag(clause_id: int, payload: TagBindRequest):
    return services.bind_tag(clause_id, payload)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
reviews_router = APIRouter(prefix="/reviews", tags=["reviews"])


@reviews_router.patch("/{review_id}/status", response_model=ReviewOut)
def change_review_status(review_id: int, payload: ReviewStatusUpdate):
    return services.change_review_status(review_id, payload)


@reviews_router.post(
    "/{review_id}/process-records",
    response_model=ProcessRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def add_process_record(review_id: int, payload: ProcessRecordCreate):
    return services.add_process_record(review_id, payload)


@reviews_router.get(
    "/{review_id}/process-records", response_model=list[ProcessRecordOut]
)
def get_process_history(review_id: int):
    return services.get_process_history(review_id)


# ---------------------------------------------------------------------------
# Risk tags
# ---------------------------------------------------------------------------
tags_router = APIRouter(prefix="/risk-tags", tags=["risk-tags"])


@tags_router.post("", response_model=RiskTagOut, status_code=status.HTTP_201_CREATED)
def create_risk_tag(payload: RiskTagCreate):
    return services.create_risk_tag(payload)


@tags_router.get("/{tag_id}/risk-distribution", response_model=TagRiskDistribution)
def tag_risk_distribution(tag_id: int):
    return services.tag_risk_distribution(tag_id)


# ---------------------------------------------------------------------------
# Reviews reporting (query by risk)
# ---------------------------------------------------------------------------
reports_router = APIRouter(tags=["reports"])


@reports_router.get("/reviews/unprocessed", response_model=list[ReviewOut])
def list_unprocessed_by_risk(risk_level: RiskLevel):
    return services.list_unprocessed_by_risk(risk_level)


@reports_router.get("/consistency-check", response_model=ConsistencyReport)
def consistency_check():
    """Self-audit the ledger and return the uniform checks report."""
    return services.run_consistency_check()

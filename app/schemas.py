"""Pydantic request/response models.

All field names are snake_case. Enums enforce the controlled vocabularies
defined in :mod:`app.enums`. Response models mirror what the repositories
return; ``created_at`` values are ISO 8601 strings produced server-side.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ClauseType,
    DocumentStatus,
    Importance,
    ImportMode,
    ProcessStatus,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_department: str = Field(min_length=1, max_length=200)
    version_no: str = Field(min_length=1, max_length=50)
    document_status: DocumentStatus = DocumentStatus.draft


class DocumentStatusUpdate(BaseModel):
    document_status: DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_department: str
    version_no: str
    document_status: DocumentStatus
    created_at: str


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
class ClauseIn(BaseModel):
    clause_no: str = Field(min_length=1, max_length=50)
    clause_text: str = Field(min_length=1)
    clause_type: ClauseType = ClauseType.other
    importance: Importance = Importance.normal


class ClauseBatchCreate(BaseModel):
    clauses: list[ClauseIn] = Field(min_length=1)


class ClauseImport(BaseModel):
    mode: ImportMode
    clauses: list[ClauseIn] = Field(min_length=1)


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    clause_no: str
    clause_text: str
    clause_type: ClauseType
    importance: Importance
    deprecated: bool


class ClauseImportMapping(BaseModel):
    """Maps a submitted clause_no to the resulting row.

    ``previous_clause_id`` is null for freshly created clauses; for updated or
    skipped clauses it equals ``final_clause_id`` (the row is reused, not
    replaced), so callers can always resolve old references to the final id.
    """

    clause_no: str
    action: str  # "created" | "updated" | "skipped"
    previous_clause_id: int | None
    final_clause_id: int


class ClauseImportResult(BaseModel):
    mode: ImportMode
    created_count: int
    updated_count: int
    skipped_count: int
    created: list[ClauseOut]
    updated: list[ClauseOut]
    skipped: list[str]  # clause_no values that were left untouched
    mapping: list[ClauseImportMapping]  # old clause_id -> final clause_id


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
class ReviewCreate(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=200)
    comment_text: str = Field(min_length=1)
    risk_level: RiskLevel


class ReviewStatusUpdate(BaseModel):
    to_status: ProcessStatus
    operator: str | None = Field(default=None, max_length=200)
    note: str | None = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_id: int
    reviewer_name: str
    comment_text: str
    risk_level: RiskLevel
    process_status: ProcessStatus
    created_at: str


# ---------------------------------------------------------------------------
# Risk tags & bindings
# ---------------------------------------------------------------------------
class RiskTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class RiskTagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: str


class TagBindRequest(BaseModel):
    tag_id: int


class ClauseTagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_id: int
    tag_id: int
    created_at: str


# ---------------------------------------------------------------------------
# Process records
# ---------------------------------------------------------------------------
class ProcessRecordCreate(BaseModel):
    from_status: ProcessStatus
    to_status: ProcessStatus
    operator: str = Field(min_length=1, max_length=200)
    note: str | None = None


class ProcessRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_id: int
    from_status: ProcessStatus
    to_status: ProcessStatus
    operator: str
    note: str | None
    created_at: str


# ---------------------------------------------------------------------------
# Composite / reporting views
# ---------------------------------------------------------------------------
class ClauseWithLatestReview(BaseModel):
    clause: ClauseOut
    latest_review: ReviewOut | None


class RiskDistributionRow(BaseModel):
    risk_level: RiskLevel
    count: int


class TagRiskDistribution(BaseModel):
    tag_id: int
    tag_name: str
    total_reviews: int
    distribution: list[RiskDistributionRow]


class DocumentCopyRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    version_no: str = Field(min_length=1, max_length=50)


class DocumentCopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_document_id: int
    target_document_id: int
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int
    created_at: str


class InheritedTag(BaseModel):
    """A risk tag inherited by a copied clause (risk classification, not status)."""

    tag_id: int
    tag_name: str


class CopyClauseMapping(BaseModel):
    source_clause_id: int
    target_clause_id: int
    clause_no: str
    inherited_tags: list[InheritedTag]


class DocumentCopyResult(BaseModel):
    source_document_id: int
    target_document_id: int
    clause_mappings: list[CopyClauseMapping]
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int
    target_document: DocumentOut


class CopyClauseDetail(BaseModel):
    """One target clause in a copy, with its origin and inheritance summary."""

    target_clause_id: int
    target_clause_no: str
    source_clause_id: int
    source_clause_no: str
    inherited_tags: list[InheritedTag]
    not_copied_summary: list[str]  # human-readable reasons for what was dropped


class DocumentCopyDetail(BaseModel):
    copy_id: int
    source_document_id: int
    target_document_id: int
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int
    created_at: str
    clauses: list[CopyClauseDetail]


# ---------------------------------------------------------------------------
# Risk board
# ---------------------------------------------------------------------------
class RiskLevelBreakdown(BaseModel):
    risk_level: RiskLevel
    unprocessed_count: int  # opinions still open at this risk level
    resolved_count: int     # opinions resolved at this risk level


class TopRiskClause(BaseModel):
    clause_id: int
    clause_no: str
    highest_risk_level: RiskLevel
    open_count: int


class UntaggedHighRiskClause(BaseModel):
    clause_id: int
    clause_no: str
    highest_risk_level: RiskLevel


class RiskBoard(BaseModel):
    document_id: int
    document_title: str
    include_deprecated: bool
    considered_clauses: int
    tagged_clause_count: int
    risk_breakdown: list[RiskLevelBreakdown]
    top_risk_clauses: list[TopRiskClause]
    untagged_high_risk_clauses: list[UntaggedHighRiskClause]


class RiskDashboard(BaseModel):
    document_id: int
    document_title: str
    total_clauses: int
    active_clauses: int
    deprecated_clauses: int
    total_reviews: int
    open_reviews: int
    risk_distribution: list[RiskDistributionRow]
    process_distribution: list["ProcessDistributionRow"]


class ProcessDistributionRow(BaseModel):
    process_status: ProcessStatus
    count: int


RiskDashboard.model_rebuild()


# ---------------------------------------------------------------------------
# Consistency self-check
# ---------------------------------------------------------------------------
class ConsistencyCheck(BaseModel):
    name: str
    passed: bool
    problem_count: int
    details: list[dict]


class ConsistencyReport(BaseModel):
    healthy: bool           # true when every check passed
    total_problems: int
    generated_at: str       # ISO 8601
    checks: list[ConsistencyCheck]

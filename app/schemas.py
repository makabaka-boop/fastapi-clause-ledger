from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    DocumentStatus,
    ImportMode,
    ProcessStatus,
    RiskLevel,
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Documents ----------

class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    source_department: str = Field(..., min_length=1, max_length=200)
    version_no: str = Field(..., min_length=1, max_length=100)
    document_status: DocumentStatus = DocumentStatus.DRAFT


class DocumentStatusUpdate(BaseModel):
    document_status: DocumentStatus


class DocumentOut(ORMBase):
    id: int
    title: str
    source_department: str
    version_no: str
    document_status: DocumentStatus
    created_at: datetime


# ---------- Clauses ----------

class ClauseCreate(BaseModel):
    clause_no: str = Field(..., min_length=1, max_length=100)
    clause_text: str = Field(..., min_length=1)
    clause_type: str = Field("general", max_length=100)
    importance: str = Field("medium", max_length=50)


class ClauseBatchCreate(BaseModel):
    clauses: list[ClauseCreate]


class ClauseImportItem(ClauseCreate):
    pass


class ClauseImportRequest(BaseModel):
    mode: ImportMode
    clauses: list[ClauseImportItem]


class ClauseOut(ORMBase):
    id: int
    document_id: int
    clause_no: str
    clause_text: str
    clause_type: str
    importance: str
    deprecated: bool
    created_at: datetime


class ClauseWithLatestComment(ClauseOut):
    latest_comment: Optional["CommentOut"] = None


class ClauseImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    clauses: list[ClauseOut]
    id_mapping: list["ClauseIdMapping"]


class ClauseIdMapping(BaseModel):
    clause_no: str
    old_id: Optional[int] = None
    final_id: int


# ---------- Comments ----------

class CommentCreate(BaseModel):
    reviewer_name: str = Field(..., min_length=1, max_length=200)
    comment_text: str = Field(..., min_length=1)
    risk_level: RiskLevel


class CommentStatusUpdate(BaseModel):
    process_status: ProcessStatus
    operator: str = Field("system", max_length=200)
    note: str = Field("", max_length=2000)


class CommentOut(ORMBase):
    id: int
    clause_id: int
    reviewer_name: str
    comment_text: str
    risk_level: RiskLevel
    process_status: ProcessStatus
    created_at: datetime


# ---------- Risk Tags ----------

class RiskTagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)


class RiskTagOut(ORMBase):
    id: int
    name: str
    description: str
    created_at: datetime


class TagBindRequest(BaseModel):
    tag_id: int


class TagBindingOut(ORMBase):
    id: int
    clause_id: int
    tag_id: int
    created_at: datetime


# ---------- Processing Records ----------

class ProcessingRecordCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    operator: str = Field("system", max_length=200)
    note: str = Field("", max_length=2000)


class ProcessingRecordOut(ORMBase):
    id: int
    comment_id: int
    from_status: ProcessStatus
    to_status: ProcessStatus
    action: str
    operator: str
    note: str
    created_at: datetime


# ---------- Document Copy ----------

class DocumentCopyRequest(BaseModel):
    new_version_no: str = Field(..., min_length=1, max_length=100)
    new_title: Optional[str] = Field(None, max_length=500)


class DocumentCopyOut(ORMBase):
    id: int
    source_document_id: int
    target_document_id: int
    copy_type: str
    created_at: datetime


class InheritedTagOut(BaseModel):
    tag_id: int
    tag_name: str


class ClauseCopyMapping(BaseModel):
    source_clause_id: int
    target_clause_id: int
    clause_no: str
    inherited_tags: list[InheritedTagOut] = []
    copied_comment_count: int = 0
    skipped_resolved_comment_count: int = 0


class DocumentCopyResult(BaseModel):
    source_document_id: int
    target_document_id: int
    clause_mappings: list[ClauseCopyMapping]
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int
    created_at: datetime


class CopyClauseDetail(BaseModel):
    source_clause_id: int
    target_clause_id: int
    clause_no: str
    source_clause_text: str
    target_clause_text: str
    inherited_tags: list[InheritedTagOut] = []
    copied_comments: list["CommentOut"] = []
    skipped_reasons: list[str] = []


class DocumentCopyDetail(BaseModel):
    source_document_id: int
    target_document_id: int
    copy_type: str
    created_at: datetime
    clauses: list[CopyClauseDetail]
    skipped_deprecated_clauses: list["DeprecatedClauseSkip"] = []


class DeprecatedClauseSkip(BaseModel):
    source_clause_id: int
    clause_no: str
    reason: str = "clause_deprecated"


# ---------- Dashboard / Stats ----------

class RiskDistributionItem(BaseModel):
    tag_id: int
    tag_name: str
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0
    total: int = 0


class DashboardSummary(BaseModel):
    document_id: int
    total_clauses: int
    deprecated_clauses: int
    total_comments: int
    open_comments: int
    accepted_comments: int
    rejected_comments: int
    resolved_comments: int
    risk_distribution: dict[str, int]
    critical_unresolved: int


class TopRiskClauseItem(BaseModel):
    clause_id: int
    clause_no: str
    clause_text: str
    highest_risk_level: RiskLevel
    unresolved_comment_count: int
    tag_names: list[str] = []


class UntaggedHighRiskClauseItem(BaseModel):
    clause_id: int
    clause_no: str
    clause_text: str
    highest_risk_level: RiskLevel
    unresolved_comment_count: int


class RiskDashboard(BaseModel):
    document_id: int
    include_deprecated: bool
    total_clauses: int
    tagged_clause_count: int
    untagged_clause_count: int
    unresolved_by_risk: dict[str, int]
    resolved_by_risk: dict[str, int]
    total_unresolved: int
    total_resolved: int
    top_risk_clauses: list[TopRiskClauseItem]
    untagged_high_risk_clauses: list[UntaggedHighRiskClauseItem]


class HealthOut(BaseModel):
    status: str
    service: str
    timestamp: datetime


class ConsistencyIssue(BaseModel):
    entity: str
    entity_id: int
    message: str
    details: dict = {}


class ConsistencyCheck(BaseModel):
    name: str
    passed: bool
    issue_count: int
    issues: list[ConsistencyIssue] = []


class ConsistencyReport(BaseModel):
    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    total_issues: int
    checked_at: datetime
    checks: list[ConsistencyCheck]


ClauseWithLatestComment.model_rebuild()
ClauseImportResult.model_rebuild()
CopyClauseDetail.model_rebuild()
DocumentCopyDetail.model_rebuild()

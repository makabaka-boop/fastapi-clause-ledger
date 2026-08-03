from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.enums import DocumentStatus
from app.schemas.common import ORMBase


class DocumentCopyRequest(BaseModel):
    new_version_no: str = Field(..., min_length=1, max_length=100)
    target_status: DocumentStatus = DocumentStatus.DRAFT
    copied_by: str = Field("system", max_length=200)


class ClauseCopyMappingItem(ORMBase):
    source_clause_id: int
    target_clause_id: int


class CopyMappingOut(ORMBase):
    id: int
    source_document_id: int
    target_document_id: int
    copied_by: str
    created_at: datetime
    clause_mappings: List[ClauseCopyMappingItem] = []


class CopiedClauseMapping(BaseModel):
    source_clause_id: int
    target_clause_id: int
    clause_no: str
    copied_tag_ids: List[int] = []


class DocumentCopyResult(BaseModel):
    source_document_id: int
    target_document_id: int
    copied_clauses: int
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int
    copy_mapping_id: int
    clause_mappings: List[CopiedClauseMapping] = []


class InheritedTagItem(BaseModel):
    tag_id: int
    tag_name: str


class CopiedClauseDetail(BaseModel):
    source_clause_id: int
    target_clause_id: int
    clause_no: str
    clause_text: str
    clause_type: str
    importance: int
    inherited_tags: List[InheritedTagItem] = []
    source_resolved_comment_count: int = 0


class SkippedClauseDetail(BaseModel):
    source_clause_id: int
    clause_no: str
    reason: str


class CopyResultDetail(BaseModel):
    source_document_id: int
    target_document_id: int
    copy_mapping_id: int
    copied_clauses: List[CopiedClauseDetail] = []
    skipped_clauses: List[SkippedClauseDetail] = []
    summary: dict

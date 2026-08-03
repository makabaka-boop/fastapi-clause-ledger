"""请求/响应模型，字段统一 snake_case，时间统一 ISO 8601 字符串。"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import DOCUMENT_STATUSES, IMPORT_MODES, PROCESS_STATUSES, RISK_LEVELS


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 文档 ----------

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_department: str = Field(min_length=1, max_length=128)
    version_no: str = Field(min_length=1, max_length=64)


class DocumentStatusUpdate(BaseModel):
    document_status: str

    @field_validator("document_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in DOCUMENT_STATUSES:
            raise ValueError(f"document_status 必须是 {list(DOCUMENT_STATUSES)} 之一")
        return v


class DocumentOut(ORMModel):
    id: int
    title: str
    source_department: str
    version_no: str
    document_status: str
    created_at: datetime


# ---------- 条款 ----------

class ClauseCreate(BaseModel):
    clause_no: str = Field(min_length=1, max_length=64)
    clause_text: str = Field(min_length=1)
    clause_type: str = Field(default="general", max_length=64)
    importance: str = Field(default="normal", max_length=32)


class ClauseBatchCreate(BaseModel):
    clauses: List[ClauseCreate] = Field(min_length=1)


class ClauseImport(ClauseBatchCreate):
    mode: str = "skip_existing"

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in IMPORT_MODES:
            raise ValueError(f"mode 只能是 {list(IMPORT_MODES)} 之一")
        return v


class ClauseOut(ORMModel):
    id: int
    document_id: int
    clause_no: str
    clause_text: str
    clause_type: str
    importance: str
    deprecated: bool
    deprecated_at: Optional[datetime] = None
    created_at: datetime


class ClauseIdMappingItem(BaseModel):
    """导入结果中旧条款 ID 与最终条款 ID 的映射。"""

    old_clause_id: Optional[int]  # 新增条款无旧 ID，为 None
    final_clause_id: int
    action: str  # created / skipped / updated


class ClauseImportResult(BaseModel):
    mode: str
    created_count: int
    updated_count: int
    skipped_count: int
    created: List[ClauseOut]
    updated: List[ClauseOut]
    skipped: List[ClauseOut]
    clause_id_mapping: List[ClauseIdMappingItem]


class ClauseWithLatestReview(BaseModel):
    clause: ClauseOut
    latest_review: Optional["ReviewOut"] = None
    tags: List["RiskTagOut"] = []


# ---------- 审阅意见 ----------

class ReviewCreate(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=128)
    comment_text: str = Field(min_length=1)
    risk_level: str

    @field_validator("risk_level")
    @classmethod
    def _check_risk(cls, v: str) -> str:
        if v not in RISK_LEVELS:
            raise ValueError(f"risk_level 必须是 {list(RISK_LEVELS)} 之一")
        return v


class ReviewStatusChange(BaseModel):
    to_status: str
    operator_name: str = Field(min_length=1, max_length=128)
    note: str = ""

    @field_validator("to_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in PROCESS_STATUSES:
            raise ValueError(f"to_status 必须是 {list(PROCESS_STATUSES)} 之一")
        return v


class ReviewOut(ORMModel):
    id: int
    clause_id: int
    reviewer_name: str
    comment_text: str
    risk_level: str
    process_status: str
    created_at: datetime


# ---------- 风险标签 ----------

class RiskTagCreate(BaseModel):
    tag_name: str = Field(min_length=1, max_length=128)
    description: str = ""


class RiskTagOut(ORMModel):
    id: int
    tag_name: str
    description: str
    created_at: datetime


class TagBindingCreate(BaseModel):
    tag_id: int


class TagBindingOut(ORMModel):
    id: int
    clause_id: int
    tag_id: int
    created_at: datetime


class TagRiskDistributionItem(BaseModel):
    risk_level: str
    open_count: int
    total_count: int


# ---------- 处理记录 ----------

class ProcessRecordCreate(BaseModel):
    to_status: str
    operator_name: str = Field(min_length=1, max_length=128)
    note: str = ""

    @field_validator("to_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in PROCESS_STATUSES:
            raise ValueError(f"to_status 必须是 {list(PROCESS_STATUSES)} 之一")
        return v


class ProcessRecordOut(ORMModel):
    id: int
    review_id: int
    from_status: Optional[str]
    to_status: str
    operator_name: str
    note: str
    created_at: datetime


# ---------- 文档复制 ----------

class DocumentCopyCreate(BaseModel):
    version_no: str = Field(min_length=1, max_length=64)
    title: Optional[str] = Field(default=None, max_length=255)


class DocumentCopyMappingOut(ORMModel):
    id: int
    source_document_id: int
    target_document_id: int
    copied_clause_count: int
    skipped_deprecated_clause_count: int
    copied_review_count: int
    copied_tag_binding_count: int
    created_at: datetime


class ClauseCopyMappingItem(BaseModel):
    """复制时旧条款与新条款的对应关系及继承的风险标签。"""

    source_clause_id: int
    target_clause_id: int
    source_clause_no: str
    target_clause_no: str
    inherited_tag_ids: List[int]


class CopyResultOut(BaseModel):
    """复制文档版本的完整结果。"""

    source_document_id: int
    target_document_id: int
    clause_mappings: List[ClauseCopyMappingItem]
    copied_clause_count: int
    copied_review_count: int
    copied_tag_count: int
    skipped_deprecated_count: int
    skipped_resolved_comment_count: int


class CopySkippedItem(BaseModel):
    item_type: str  # clause / review
    source_clause_id: int
    clause_no: str
    source_review_id: Optional[int] = None
    reason: str  # deprecated_clause / resolved_review


class CopyClauseDetail(BaseModel):
    """目标文档中某个新条款的复制来源详情。"""

    target_clause_id: int
    target_clause_no: str
    source_clause_id: int
    source_clause_no: str
    inherited_tags: List["RiskTagOut"]
    skipped_items: List[CopySkippedItem]  # 该条款下未复制的内容及原因


class CopyDetailsOut(BaseModel):
    source_document_id: int
    target_document_id: int
    clauses: List[CopyClauseDetail]
    skipped_clauses: List[CopySkippedItem]  # 文档级未复制条款（已废弃）


# ---------- 一致性自检 ----------

class ConsistencyCheckItem(BaseModel):
    check_name: str
    passed: bool
    issue_count: int
    details: List[dict] = []


class ConsistencyReport(BaseModel):
    overall_passed: bool
    check_count: int
    failed_count: int
    checks: List[ConsistencyCheckItem]
    checked_at: str  # ISO 8601


# ---------- 风险看板 ----------

class RiskClauseItem(BaseModel):
    clause_id: int
    clause_no: str
    risk_level: str


class DocumentRiskDashboard(BaseModel):
    document_id: int
    title: str
    version_no: str
    include_deprecated: bool
    clause_count: int
    deprecated_clause_count: int
    review_count: int
    open_review_count: int
    risk_distribution: dict
    status_distribution: dict
    open_risk_distribution: dict  # 各风险等级未处理数量（不含 resolved）
    resolved_risk_distribution: dict  # 各风险等级已解决数量
    highest_risk_level: Optional[str]
    highest_risk_clauses: List[RiskClauseItem]
    tagged_clause_count: int  # 绑定至少一个风险标签的条款数
    untagged_high_risk_clauses: List[RiskClauseItem]  # 无标签高风险条款


ClauseWithLatestReview.model_rebuild()

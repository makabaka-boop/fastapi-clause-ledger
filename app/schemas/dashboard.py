from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from app.enums import RiskLevel
from app.schemas.common import ORMBase


class RiskLevelSummary(BaseModel):
    low: int
    medium: int
    high: int
    critical: int
    total: int


class ProcessStatusSummary(BaseModel):
    open: int
    accepted: int
    rejected: int
    resolved: int


class DocumentDashboard(BaseModel):
    document_id: int
    total_clauses: int
    deprecated_clauses: int
    active_clauses: int
    total_comments: int
    open_comments: int
    risk_by_level: RiskLevelSummary
    status_by_process: ProcessStatusSummary
    tag_distribution: List[Dict]


class DashboardClauseItem(BaseModel):
    clause_id: int
    clause_no: str
    clause_type: str
    importance: int
    highest_risk_level: Optional[RiskLevel] = None
    unresolved_comment_count: int = 0
    latest_comment_text: Optional[str] = None


class RiskDashboard(BaseModel):
    document_id: int
    include_deprecated: bool
    unresolved_by_risk: RiskLevelSummary
    resolved_count: int
    highest_risk_clauses: List[DashboardClauseItem]
    tagged_clause_count: int
    untagged_high_risk_clauses: List[DashboardClauseItem]

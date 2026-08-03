from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.enums import ProcessStatus, RiskLevel
from app.schemas.common import ORMBase


class CommentCreate(BaseModel):
    reviewer_name: str = Field(..., min_length=1, max_length=200)
    comment_text: str = Field(..., min_length=1)
    risk_level: RiskLevel


class CommentStatusUpdate(BaseModel):
    process_status: ProcessStatus
    note: str = ""
    operator: Optional[str] = None


class CommentOut(ORMBase):
    id: int
    clause_id: int
    reviewer_name: str
    comment_text: str
    risk_level: RiskLevel
    process_status: ProcessStatus
    created_at: datetime


class ClauseWithLatestComment(ORMBase):
    id: int
    document_id: int
    clause_no: str
    clause_text: str
    clause_type: str
    importance: int
    deprecated: bool
    created_at: datetime
    latest_comment: Optional[CommentOut] = None

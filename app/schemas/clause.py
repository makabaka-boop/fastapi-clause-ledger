from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.enums import ImportMode
from app.schemas.common import ORMBase


class ClauseItem(BaseModel):
    clause_no: str = Field(..., min_length=1, max_length=100)
    clause_text: str = Field(..., min_length=1)
    clause_type: str = Field(..., min_length=1, max_length=100)
    importance: int = Field(1, ge=1, le=5)


class ClauseBatchCreate(BaseModel):
    clauses: List[ClauseItem] = Field(..., min_length=1)


class ClauseImportItem(ClauseItem):
    pass


class ClauseImportRequest(BaseModel):
    mode: ImportMode
    clauses: List[ClauseImportItem] = Field(..., min_length=1)


class ClauseOut(ORMBase):
    id: int
    document_id: int
    clause_no: str
    clause_text: str
    clause_type: str
    importance: int
    deprecated: bool
    created_at: datetime


class ClauseDeprecateOut(ORMBase):
    id: int
    document_id: int
    clause_no: str
    deprecated: bool


class ClauseIdMapping(BaseModel):
    clause_no: str
    old_clause_id: Optional[int] = None
    final_clause_id: int
    action: str


class ClauseImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    clause_ids: List[int]
    id_mappings: List[ClauseIdMapping]


class ClauseBatchResult(BaseModel):
    created: int
    clause_ids: List[int]

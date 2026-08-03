from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.enums import DocumentStatus
from app.schemas.common import ORMBase


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

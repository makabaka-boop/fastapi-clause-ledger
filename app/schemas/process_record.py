from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.enums import ProcessStatus
from app.schemas.common import ORMBase


class ProcessRecordCreate(BaseModel):
    note: str = Field("", max_length=2000)
    operator: str = Field("system", max_length=200)


class ProcessRecordOut(ORMBase):
    id: int
    comment_id: int
    from_status: ProcessStatus
    to_status: ProcessStatus
    note: str
    operator: str
    created_at: datetime

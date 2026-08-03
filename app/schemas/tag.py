from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class TagOut(ORMBase):
    id: int
    name: str


class TagBindRequest(BaseModel):
    clause_id: int
    tag_id: int


class TagBindingOut(ORMBase):
    id: int
    clause_id: int
    tag_id: int


class TagRiskDistributionItem(BaseModel):
    tag_id: int
    tag_name: str
    low: int
    medium: int
    high: int
    critical: int
    total: int

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    DocumentCopyMappingOut,
    RiskTagCreate,
    RiskTagOut,
    TagRiskDistributionItem,
)
from ..services.copy_service import CopyService
from ..services.tag_service import TagService

router = APIRouter(tags=["tags"])


@router.post("/tags", response_model=RiskTagOut, status_code=201)
def create_tag(data: RiskTagCreate, db: Session = Depends(get_db)):
    return TagService(db).create_tag(data)


@router.get("/tags", response_model=List[RiskTagOut])
def list_tags(db: Session = Depends(get_db)):
    from ..repositories.tags import TagRepository

    return TagRepository(db).list_all()


@router.get("/tags/{tag_id}/risk_distribution", response_model=List[TagRiskDistributionItem])
def tag_risk_distribution(tag_id: int, db: Session = Depends(get_db)):
    return TagService(db).risk_distribution(tag_id)


@router.get("/copies", response_model=List[DocumentCopyMappingOut])
def list_copy_mappings(
    document_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    return CopyService(db).list_mappings(document_id)

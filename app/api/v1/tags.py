from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_tag_service
from app.schemas.tag import (
    TagBindRequest,
    TagBindingOut,
    TagCreate,
    TagOut,
    TagRiskDistributionItem,
)
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.post(
    "",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    payload: TagCreate,
    service: TagService = Depends(get_tag_service),
):
    return service.create_tag(payload)


@router.get("", response_model=List[TagOut])
def list_tags(
    service: TagService = Depends(get_tag_service),
):
    return service.list_tags()


@router.get(
    "/risk-distribution",
    response_model=List[TagRiskDistributionItem],
)
def risk_distribution(
    document_id: Optional[int] = Query(None),
    service: TagService = Depends(get_tag_service),
):
    return service.risk_distribution(document_id=document_id)


@router.post(
    "/bindings",
    response_model=TagBindingOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_tag(
    payload: TagBindRequest,
    service: TagService = Depends(get_tag_service),
):
    return service.bind_tag(payload)


@router.get("/{tag_id}", response_model=TagOut)
def get_tag(
    tag_id: int,
    service: TagService = Depends(get_tag_service),
):
    return service.get_tag(tag_id)

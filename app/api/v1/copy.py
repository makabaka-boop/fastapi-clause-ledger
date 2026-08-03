from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_copy_service
from app.schemas.copy import (
    CopyMappingOut,
    CopyResultDetail,
    DocumentCopyRequest,
    DocumentCopyResult,
)
from app.services.copy_service import CopyService

router = APIRouter(tags=["copy"])


@router.post(
    "/documents/{document_id}/copy",
    response_model=DocumentCopyResult,
    status_code=status.HTTP_201_CREATED,
)
def copy_document(
    document_id: int,
    payload: DocumentCopyRequest,
    service: CopyService = Depends(get_copy_service),
):
    return service.copy_document(document_id, payload)


@router.get(
    "/documents/{target_document_id}/copy-detail",
    response_model=CopyResultDetail,
)
def get_copy_detail(
    target_document_id: int,
    service: CopyService = Depends(get_copy_service),
):
    return service.get_copy_detail(target_document_id)


@router.get(
    "/copy-mappings",
    response_model=List[CopyMappingOut],
)
def list_copy_mappings(
    source_document_id: Optional[int] = Query(None),
    target_document_id: Optional[int] = Query(None),
    service: CopyService = Depends(get_copy_service),
):
    return service.list_mappings(
        source_document_id=source_document_id,
        target_document_id=target_document_id,
    )


@router.get(
    "/copy-mappings/{mapping_id}",
    response_model=CopyMappingOut,
)
def get_copy_mapping(
    mapping_id: int,
    service: CopyService = Depends(get_copy_service),
):
    return service.get_mapping(mapping_id)

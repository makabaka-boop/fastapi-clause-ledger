from typing import List

from fastapi import APIRouter, Depends, status

from app.api.deps import get_document_service
from app.schemas.document import (
    DocumentCreate,
    DocumentOut,
    DocumentStatusUpdate,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: DocumentCreate,
    service: DocumentService = Depends(get_document_service),
):
    return service.create_document(payload)


@router.get("", response_model=List[DocumentOut])
def list_documents(
    service: DocumentService = Depends(get_document_service),
):
    return service.list_documents()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
):
    return service.get_document(document_id)


@router.patch("/{document_id}/status", response_model=DocumentOut)
def update_document_status(
    document_id: int,
    payload: DocumentStatusUpdate,
    service: DocumentService = Depends(get_document_service),
):
    return service.update_status(document_id, payload)

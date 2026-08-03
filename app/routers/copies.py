from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

router = APIRouter(tags=["document-copies"])


@router.post(
    "/documents/{document_id}/copy",
    response_model=schemas.DocumentCopyResult,
    status_code=status.HTTP_201_CREATED,
)
def copy_document(
    document_id: int,
    payload: schemas.DocumentCopyRequest,
    db: Session = Depends(get_db),
) -> schemas.DocumentCopyResult:
    service = services.DocumentCopyService(db)
    return service.copy_document(document_id, payload)


@router.get(
    "/document-copies/{target_document_id}/detail",
    response_model=schemas.DocumentCopyDetail,
)
def get_copy_detail(
    target_document_id: int,
    db: Session = Depends(get_db),
) -> schemas.DocumentCopyDetail:
    service = services.DocumentCopyService(db)
    return service.get_copy_detail(target_document_id)


@router.get(
    "/document-copies",
    response_model=list[schemas.DocumentCopyOut],
)
def list_copy_mappings(
    db: Session = Depends(get_db),
) -> list[schemas.DocumentCopyOut]:
    service = services.DocumentCopyService(db)
    mappings = service.list_copy_mappings()
    return [schemas.DocumentCopyOut.model_validate(m) for m in mappings]


@router.get(
    "/documents/{document_id}/copy-mappings",
    response_model=list[schemas.DocumentCopyOut],
)
def list_copy_mappings_by_source(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[schemas.DocumentCopyOut]:
    service = services.DocumentCopyService(db)
    mappings = service.list_by_source(document_id)
    return [schemas.DocumentCopyOut.model_validate(m) for m in mappings]

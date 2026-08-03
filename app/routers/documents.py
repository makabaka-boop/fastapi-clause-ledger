from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=schemas.DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: schemas.DocumentCreate,
    db: Session = Depends(get_db),
) -> schemas.DocumentOut:
    service = services.DocumentService(db)
    doc = service.create_document(payload)
    return schemas.DocumentOut.model_validate(doc)


@router.get(
    "/{document_id}",
    response_model=schemas.DocumentOut,
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> schemas.DocumentOut:
    service = services.DocumentService(db)
    doc = service.get_document(document_id)
    return schemas.DocumentOut.model_validate(doc)


@router.patch(
    "/{document_id}/status",
    response_model=schemas.DocumentOut,
)
def update_document_status(
    document_id: int,
    payload: schemas.DocumentStatusUpdate,
    db: Session = Depends(get_db),
) -> schemas.DocumentOut:
    service = services.DocumentService(db)
    doc = service.update_status(document_id, payload)
    return schemas.DocumentOut.model_validate(doc)


@router.get(
    "",
    response_model=list[schemas.DocumentOut],
)
def list_documents(
    db: Session = Depends(get_db),
) -> list[schemas.DocumentOut]:
    service = services.DocumentService(db)
    docs = service.list_documents()
    return [schemas.DocumentOut.model_validate(d) for d in docs]

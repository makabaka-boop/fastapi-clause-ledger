from typing import List

from sqlalchemy.orm import Session

from app.exceptions.app_exceptions import NotFoundError
from app.models.document import Document
from app.repositories.document_repo import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentStatusUpdate


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.document_repo = DocumentRepository(db)

    def create_document(self, payload: DocumentCreate) -> Document:
        document = self.document_repo.create(
            title=payload.title,
            source_department=payload.source_department,
            version_no=payload.version_no,
            document_status=payload.document_status.value,
        )
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_status(
        self, document_id: int, payload: DocumentStatusUpdate
    ) -> Document:
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )
        self.document_repo.update_status(
            document, payload.document_status.value
        )
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_document(self, document_id: int) -> Document:
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )
        return document

    def list_documents(self) -> List[Document]:
        return self.document_repo.list_all()

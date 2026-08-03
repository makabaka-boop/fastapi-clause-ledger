from sqlalchemy.orm import Session

from ..exceptions import NotFoundError
from ..models import Document
from ..repositories.documents import DocumentRepository
from ..schemas import DocumentCreate


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)

    def get_or_404(self, document_id: int) -> Document:
        doc = self.repo.get(document_id)
        if doc is None:
            raise NotFoundError(f"文档不存在: {document_id}", {"document_id": document_id})
        return doc

    def create_document(self, data: DocumentCreate) -> Document:
        doc = self.repo.create(data.title, data.source_department, data.version_no)
        self.db.commit()
        return doc

    def update_status(self, document_id: int, status: str) -> Document:
        doc = self.get_or_404(document_id)
        doc = self.repo.update_status(doc, status)
        self.db.commit()
        return doc

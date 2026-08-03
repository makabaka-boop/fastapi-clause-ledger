from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, title: str, source_department: str, version_no: str) -> Document:
        doc = Document(title=title, source_department=source_department, version_no=version_no)
        self.db.add(doc)
        self.db.flush()
        return doc

    def get(self, document_id: int) -> Optional[Document]:
        return self.db.get(Document, document_id)

    def update_status(self, doc: Document, status: str) -> Document:
        doc.document_status = status
        self.db.flush()
        return doc

    def list_all(self) -> List[Document]:
        return list(self.db.scalars(select(Document).order_by(Document.id)).all())

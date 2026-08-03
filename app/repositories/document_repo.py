from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, db: Session):
        super().__init__(Document, db)

    def get_by_id(self, document_id: int) -> Optional[Document]:
        return self.db.get(Document, document_id)

    def list_all(self) -> List[Document]:
        return list(
            self.db.execute(select(Document).order_by(Document.id)).scalars().all()
        )

    def create(
        self,
        title: str,
        source_department: str,
        version_no: str,
        document_status: str,
    ) -> Document:
        doc = Document(
            title=title,
            source_department=source_department,
            version_no=version_no,
            document_status=document_status,
        )
        return self.add(doc)

    def update_status(self, document: Document, new_status: str) -> Document:
        document.document_status = new_status
        self.db.flush()
        self.db.refresh(document)
        return document

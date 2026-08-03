from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CopyItem, DocumentCopyMapping


class CopyMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, source_document_id: int, target_document_id: int, **stats) -> DocumentCopyMapping:
        mapping = DocumentCopyMapping(
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            **stats,
        )
        self.db.add(mapping)
        self.db.flush()
        return mapping

    def get(self, mapping_id: int) -> Optional[DocumentCopyMapping]:
        return self.db.get(DocumentCopyMapping, mapping_id)

    def get_by_target_document(self, target_document_id: int) -> Optional[DocumentCopyMapping]:
        stmt = (
            select(DocumentCopyMapping)
            .where(DocumentCopyMapping.target_document_id == target_document_id)
            .order_by(DocumentCopyMapping.id.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_all(self, document_id: Optional[int] = None) -> List[DocumentCopyMapping]:
        stmt = select(DocumentCopyMapping).order_by(DocumentCopyMapping.id)
        if document_id is not None:
            stmt = stmt.where(
                (DocumentCopyMapping.source_document_id == document_id)
                | (DocumentCopyMapping.target_document_id == document_id)
            )
        return list(self.db.scalars(stmt).all())

    def add_item(self, mapping_id: int, **fields) -> CopyItem:
        item = CopyItem(mapping_id=mapping_id, **fields)
        self.db.add(item)
        self.db.flush()
        return item

    def list_items(self, mapping_id: int) -> List[CopyItem]:
        stmt = select(CopyItem).where(CopyItem.mapping_id == mapping_id).order_by(CopyItem.id)
        return list(self.db.scalars(stmt).all())

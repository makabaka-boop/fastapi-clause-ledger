from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.copy_mapping import CopyMapping, ClauseCopyMapping
from app.repositories.base import BaseRepository


class CopyMappingRepository(BaseRepository[CopyMapping]):
    def __init__(self, db: Session):
        super().__init__(CopyMapping, db)

    def get_by_id(self, mapping_id: int) -> Optional[CopyMapping]:
        return self.db.get(CopyMapping, mapping_id)

    def list_by_source_document(self, document_id: int) -> List[CopyMapping]:
        stmt = (
            select(CopyMapping)
            .where(CopyMapping.source_document_id == document_id)
            .order_by(CopyMapping.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_target_document(self, document_id: int) -> List[CopyMapping]:
        stmt = (
            select(CopyMapping)
            .where(CopyMapping.target_document_id == document_id)
            .order_by(CopyMapping.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_all(self) -> List[CopyMapping]:
        stmt = select(CopyMapping).order_by(CopyMapping.id)
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        source_document_id: int,
        target_document_id: int,
        copied_by: str,
    ) -> CopyMapping:
        mapping = CopyMapping(
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            copied_by=copied_by,
        )
        self.db.add(mapping)
        self.db.flush()
        self.db.refresh(mapping)
        return mapping

    def add_clause_mapping(
        self,
        copy_mapping_id: int,
        source_clause_id: int,
        target_clause_id: int,
    ) -> ClauseCopyMapping:
        cm = ClauseCopyMapping(
            copy_mapping_id=copy_mapping_id,
            source_clause_id=source_clause_id,
            target_clause_id=target_clause_id,
        )
        self.db.add(cm)
        self.db.flush()
        self.db.refresh(cm)
        return cm

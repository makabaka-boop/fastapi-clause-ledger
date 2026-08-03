from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clause import Clause
from app.repositories.base import BaseRepository


class ClauseRepository(BaseRepository[Clause]):
    def __init__(self, db: Session):
        super().__init__(Clause, db)

    def get_by_id(self, clause_id: int) -> Optional[Clause]:
        return self.db.get(Clause, clause_id)

    def get_by_document_and_no(
        self, document_id: int, clause_no: str
    ) -> Optional[Clause]:
        stmt = select(Clause).where(
            Clause.document_id == document_id,
            Clause.clause_no == clause_no,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_document(self, document_id: int) -> List[Clause]:
        stmt = (
            select(Clause)
            .where(Clause.document_id == document_id)
            .order_by(Clause.clause_no)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_active_by_document(self, document_id: int) -> List[Clause]:
        stmt = (
            select(Clause)
            .where(
                Clause.document_id == document_id,
                Clause.deprecated.is_(False),
            )
            .order_by(Clause.clause_no)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_deprecated_by_document(self, document_id: int) -> List[Clause]:
        stmt = (
            select(Clause)
            .where(
                Clause.document_id == document_id,
                Clause.deprecated.is_(True),
            )
            .order_by(Clause.clause_no)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        document_id: int,
        clause_no: str,
        clause_text: str,
        clause_type: str,
        importance: int,
    ) -> Clause:
        clause = Clause(
            document_id=document_id,
            clause_no=clause_no,
            clause_text=clause_text,
            clause_type=clause_type,
            importance=importance,
            deprecated=False,
        )
        return self.add(clause)

    def deprecate(self, clause: Clause) -> Clause:
        clause.deprecated = True
        self.db.flush()
        self.db.refresh(clause)
        return clause

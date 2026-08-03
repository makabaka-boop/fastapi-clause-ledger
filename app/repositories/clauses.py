from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Clause, utcnow


class ClauseRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, clause_id: int) -> Optional[Clause]:
        return self.db.get(Clause, clause_id)

    def get_by_no(self, document_id: int, clause_no: str) -> Optional[Clause]:
        stmt = select(Clause).where(
            Clause.document_id == document_id, Clause.clause_no == clause_no
        )
        return self.db.scalars(stmt).first()

    def list_by_document(self, document_id: int, include_deprecated: bool = True) -> List[Clause]:
        stmt = select(Clause).where(Clause.document_id == document_id).order_by(Clause.id)
        if not include_deprecated:
            stmt = stmt.where(Clause.deprecated.is_(False))
        return list(self.db.scalars(stmt).all())

    def create(self, document_id: int, data) -> Clause:
        clause = Clause(
            document_id=document_id,
            clause_no=data.clause_no,
            clause_text=data.clause_text,
            clause_type=data.clause_type,
            importance=data.importance,
        )
        self.db.add(clause)
        self.db.flush()
        return clause

    def update(self, clause: Clause, data) -> Clause:
        clause.clause_text = data.clause_text
        clause.clause_type = data.clause_type
        clause.importance = data.importance
        self.db.flush()
        return clause

    def deprecate(self, clause: Clause) -> Clause:
        clause.deprecated = True
        clause.deprecated_at = utcnow()
        self.db.flush()
        return clause

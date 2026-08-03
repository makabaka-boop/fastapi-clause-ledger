from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import TERMINAL_PROCESS_STATUSES
from app.models.comment import Comment
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    def __init__(self, db: Session):
        super().__init__(Comment, db)

    def get_by_id(self, comment_id: int) -> Optional[Comment]:
        return self.db.get(Comment, comment_id)

    def list_by_clause(self, clause_id: int) -> List[Comment]:
        stmt = (
            select(Comment)
            .where(Comment.clause_id == clause_id)
            .order_by(Comment.created_at.desc(), Comment.id.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_resolved_by_clause(self, clause_id: int) -> int:
        stmt = (
            select(func.count(Comment.id))
            .where(
                Comment.clause_id == clause_id,
                Comment.process_status == "resolved",
            )
        )
        return self.db.execute(stmt).scalar_one()

    def count_resolved_by_clauses(
        self, clause_ids: List[int]
    ) -> Dict[int, int]:
        if not clause_ids:
            return {}
        stmt = (
            select(
                Comment.clause_id.label("clause_id"),
                func.count(Comment.id).label("cnt"),
            )
            .where(
                Comment.clause_id.in_(clause_ids),
                Comment.process_status == "resolved",
            )
            .group_by(Comment.clause_id)
        )
        rows = self.db.execute(stmt).all()
        return {row.clause_id: row.cnt for row in rows}

    def get_latest_by_clause(self, clause_id: int) -> Optional[Comment]:
        stmt = (
            select(Comment)
            .where(Comment.clause_id == clause_id)
            .order_by(Comment.created_at.desc(), Comment.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_document(self, document_id: int) -> List[Comment]:
        from app.models.clause import Clause

        stmt = (
            select(Comment)
            .join(Clause, Clause.id == Comment.clause_id)
            .where(Clause.document_id == document_id)
            .order_by(Comment.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_unresolved_by_risk(
        self, risk_level: str, document_id: Optional[int] = None
    ) -> List[Comment]:
        from app.models.clause import Clause

        stmt = (
            select(Comment)
            .join(Clause, Clause.id == Comment.clause_id)
            .where(
                Comment.risk_level == risk_level,
                Comment.process_status.notin_(list(TERMINAL_PROCESS_STATUSES)),
            )
        )
        if document_id is not None:
            stmt = stmt.where(Clause.document_id == document_id)
        stmt = stmt.order_by(Comment.id)
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        clause_id: int,
        reviewer_name: str,
        comment_text: str,
        risk_level: str,
    ) -> Comment:
        comment = Comment(
            clause_id=clause_id,
            reviewer_name=reviewer_name,
            comment_text=comment_text,
            risk_level=risk_level,
            process_status="open",
        )
        return self.add(comment)

    def update_status(self, comment: Comment, new_status: str) -> Comment:
        comment.process_status = new_status
        self.db.flush()
        self.db.refresh(comment)
        return comment

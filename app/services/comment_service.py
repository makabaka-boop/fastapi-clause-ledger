from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.enums import ProcessStatus, RiskLevel
from app.exceptions.app_exceptions import (
    BusinessRuleError,
    NotFoundError,
)
from app.models.comment import Comment
from app.repositories.clause_repo import ClauseRepository
from app.repositories.comment_repo import CommentRepository
from app.repositories.document_repo import DocumentRepository
from app.schemas.comment import CommentCreate, CommentStatusUpdate
from app.state_machine import comment_state
from app.services.process_service import ProcessService


class CommentService:
    def __init__(self, db: Session):
        self.db = db
        self.comment_repo = CommentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.document_repo = DocumentRepository(db)
        self.process_service = ProcessService(db)

    def _get_clause_or_raise(self, clause_id: int):
        clause = self.clause_repo.get_by_id(clause_id)
        if clause is None:
            raise NotFoundError(
                message="Clause not found",
                details={"clause_id": clause_id},
            )
        return clause

    def add_comment(self, clause_id: int, payload: CommentCreate) -> Comment:
        clause = self._get_clause_or_raise(clause_id)
        if clause.deprecated:
            raise BusinessRuleError(
                message="Cannot add comment to a deprecated clause",
                details={"clause_id": clause_id},
            )

        comment = self.comment_repo.create(
            clause_id=clause_id,
            reviewer_name=payload.reviewer_name,
            comment_text=payload.comment_text,
            risk_level=payload.risk_level.value,
        )
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def change_status(
        self,
        comment_id: int,
        payload: CommentStatusUpdate,
    ) -> Comment:
        comment = self.comment_repo.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                message="Comment not found",
                details={"comment_id": comment_id},
            )

        clause = self.clause_repo.get_by_id(comment.clause_id)
        if clause is not None and clause.deprecated:
            current_status = ProcessStatus(comment.process_status)
            if current_status in (
                ProcessStatus.OPEN,
                ProcessStatus.ACCEPTED,
            ):
                raise BusinessRuleError(
                    message="Cannot change status of an unresolved comment "
                    "on a deprecated clause",
                    details={
                        "comment_id": comment_id,
                        "clause_id": comment.clause_id,
                        "current_status": current_status.value,
                    },
                )

        current = ProcessStatus(comment.process_status)
        target = payload.process_status

        comment_state.validate_transition(current, target)

        if comment_state.requires_record(current, target):
            operator = payload.operator or "system"
            self.process_service._create_record(
                comment_id=comment_id,
                from_status=current,
                to_status=target,
                note=payload.note,
                operator=operator,
            )

        self.comment_repo.update_status(comment, target.value)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_comment(self, comment_id: int) -> Comment:
        comment = self.comment_repo.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                message="Comment not found",
                details={"comment_id": comment_id},
            )
        return comment

    def list_clauses_with_latest_comments(
        self, document_id: int
    ) -> List[Dict]:
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )

        clauses = self.clause_repo.list_by_document(document_id)
        result = []
        for clause in clauses:
            latest = self.comment_repo.get_latest_by_clause(clause.id)
            item = {
                "id": clause.id,
                "document_id": clause.document_id,
                "clause_no": clause.clause_no,
                "clause_text": clause.clause_text,
                "clause_type": clause.clause_type,
                "importance": clause.importance,
                "deprecated": clause.deprecated,
                "created_at": clause.created_at,
                "latest_comment": latest,
            }
            result.append(item)
        return result

    def list_unresolved_by_risk(
        self,
        risk_level: RiskLevel,
        document_id: Optional[int] = None,
    ) -> List[Comment]:
        if document_id is not None:
            doc = self.document_repo.get_by_id(document_id)
            if doc is None:
                raise NotFoundError(
                    message="Document not found",
                    details={"document_id": document_id},
                )
        return self.comment_repo.list_unresolved_by_risk(
            risk_level.value, document_id=document_id
        )

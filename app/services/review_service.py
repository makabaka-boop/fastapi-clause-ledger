from typing import List

from sqlalchemy.orm import Session

from ..exceptions import NotFoundError, ValidationError
from ..models import ProcessRecord, Review
from ..repositories.records import ProcessRecordRepository
from ..repositories.reviews import ReviewRepository
from ..schemas import ProcessRecordCreate, ReviewCreate, ReviewStatusChange
from ..state_machine import requires_process_record, validate_transition
from .clause_service import ClauseService


class ReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReviewRepository(db)
        self.record_repo = ProcessRecordRepository(db)
        self.clause_service = ClauseService(db)

    def get_or_404(self, review_id: int) -> Review:
        review = self.repo.get(review_id)
        if review is None:
            raise NotFoundError(f"审阅意见不存在: {review_id}", {"review_id": review_id})
        return review

    def add_review(self, clause_id: int, data: ReviewCreate) -> Review:
        clause = self.clause_service.get_or_404(clause_id)
        self.clause_service.ensure_not_deprecated(clause)
        review = self.repo.create(
            clause_id, data.reviewer_name, data.comment_text, data.risk_level
        )
        self.db.commit()
        return review

    def change_status(self, review_id: int, data: ReviewStatusChange) -> Review:
        review = self.get_or_404(review_id)
        self.clause_service.ensure_not_deprecated(review.clause)
        validate_transition(review.process_status, data.to_status)
        if requires_process_record(review.process_status, data.to_status) and not data.operator_name:
            raise ValidationError(
                "该状态流转必须写入处理记录（operator_name 必填）",
                {"from_status": review.process_status, "to_status": data.to_status},
            )
        from_status = review.process_status
        review = self.repo.update_status(review, data.to_status)
        self.record_repo.create(
            review_id=review.id,
            from_status=from_status,
            to_status=data.to_status,
            operator_name=data.operator_name,
            note=data.note,
        )
        self.db.commit()
        return review

    def write_process_record(self, review_id: int, data: ProcessRecordCreate) -> ProcessRecord:
        """写入处理记录并同步意见状态（遵循状态机约束）。"""
        review = self.get_or_404(review_id)
        self.clause_service.ensure_not_deprecated(review.clause)
        validate_transition(review.process_status, data.to_status)
        record = self.record_repo.create(
            review_id=review.id,
            from_status=review.process_status,
            to_status=data.to_status,
            operator_name=data.operator_name,
            note=data.note,
        )
        self.repo.update_status(review, data.to_status)
        self.db.commit()
        return record

    def list_history(self, review_id: int) -> List[ProcessRecord]:
        self.get_or_404(review_id)
        return self.record_repo.list_by_review(review_id)

    def list_open_by_risk_level(self, risk_level: str) -> List[Review]:
        return self.repo.list_open_by_risk_level(risk_level)

    def list_by_clause(self, clause_id: int) -> List[Review]:
        """条款的历史意见（废弃条款同样可查）。"""
        self.clause_service.get_or_404(clause_id)
        return self.repo.list_by_clause(clause_id)

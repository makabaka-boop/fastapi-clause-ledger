from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Review


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, review_id: int) -> Optional[Review]:
        return self.db.get(Review, review_id)

    def create(self, clause_id: int, reviewer_name: str, comment_text: str, risk_level: str) -> Review:
        review = Review(
            clause_id=clause_id,
            reviewer_name=reviewer_name,
            comment_text=comment_text,
            risk_level=risk_level,
            process_status="open",
        )
        self.db.add(review)
        self.db.flush()
        return review

    def update_status(self, review: Review, to_status: str) -> Review:
        review.process_status = to_status
        self.db.flush()
        return review

    def latest_for_clause(self, clause_id: int) -> Optional[Review]:
        stmt = (
            select(Review)
            .where(Review.clause_id == clause_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_open_by_risk_level(self, risk_level: str) -> List[Review]:
        stmt = (
            select(Review)
            .where(Review.risk_level == risk_level, Review.process_status == "open")
            .order_by(Review.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_by_clause(self, clause_id: int) -> List[Review]:
        stmt = select(Review).where(Review.clause_id == clause_id).order_by(Review.id)
        return list(self.db.scalars(stmt).all())

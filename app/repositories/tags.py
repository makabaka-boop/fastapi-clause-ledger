from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Clause, ClauseTagBinding, Review, RiskTag


class TagRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, tag_id: int) -> Optional[RiskTag]:
        return self.db.get(RiskTag, tag_id)

    def get_by_name(self, tag_name: str) -> Optional[RiskTag]:
        return self.db.scalars(select(RiskTag).where(RiskTag.tag_name == tag_name)).first()

    def create(self, tag_name: str, description: str) -> RiskTag:
        tag = RiskTag(tag_name=tag_name, description=description)
        self.db.add(tag)
        self.db.flush()
        return tag

    def list_all(self) -> List[RiskTag]:
        return list(self.db.scalars(select(RiskTag).order_by(RiskTag.id)).all())

    def get_binding(self, clause_id: int, tag_id: int) -> Optional[ClauseTagBinding]:
        stmt = select(ClauseTagBinding).where(
            ClauseTagBinding.clause_id == clause_id, ClauseTagBinding.tag_id == tag_id
        )
        return self.db.scalars(stmt).first()

    def bind(self, clause_id: int, tag_id: int) -> ClauseTagBinding:
        binding = ClauseTagBinding(clause_id=clause_id, tag_id=tag_id)
        self.db.add(binding)
        self.db.flush()
        return binding

    def list_tags_for_clause(self, clause_id: int) -> List[RiskTag]:
        stmt = (
            select(RiskTag)
            .join(ClauseTagBinding, ClauseTagBinding.tag_id == RiskTag.id)
            .where(ClauseTagBinding.clause_id == clause_id)
            .order_by(RiskTag.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_bindings_for_clause(self, clause_id: int) -> List[ClauseTagBinding]:
        stmt = select(ClauseTagBinding).where(ClauseTagBinding.clause_id == clause_id)
        return list(self.db.scalars(stmt).all())

    def risk_distribution(self, tag_id: int) -> List[dict]:
        """该标签下所有条款关联意见的风险等级分布。"""
        stmt = (
            select(Review.risk_level, Review.process_status, func.count())
            .join(Clause, Review.clause_id == Clause.id)
            .join(ClauseTagBinding, ClauseTagBinding.clause_id == Clause.id)
            .where(ClauseTagBinding.tag_id == tag_id)
            .group_by(Review.risk_level, Review.process_status)
        )
        rows = self.db.execute(stmt).all()
        return [
            {"risk_level": r, "process_status": s, "count": c} for r, s, c in rows
        ]

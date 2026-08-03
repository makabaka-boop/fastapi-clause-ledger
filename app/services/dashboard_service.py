from typing import List, Optional

from sqlalchemy.orm import Session

from ..constants import HIGH_RISK_LEVELS, PROCESS_STATUSES, RISK_LEVELS, RISK_ORDER
from ..repositories.clauses import ClauseRepository
from ..repositories.reviews import ReviewRepository
from ..repositories.tags import TagRepository
from ..schemas import (
    ClauseOut,
    ClauseWithLatestReview,
    DocumentRiskDashboard,
    ReviewOut,
    RiskClauseItem,
    RiskTagOut,
)
from .document_service import DocumentService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.doc_service = DocumentService(db)
        self.clause_repo = ClauseRepository(db)
        self.review_repo = ReviewRepository(db)
        self.tag_repo = TagRepository(db)

    def clauses_with_latest_review(self, document_id: int) -> List[ClauseWithLatestReview]:
        self.doc_service.get_or_404(document_id)
        result = []
        for clause in self.clause_repo.list_by_document(document_id):
            latest = self.review_repo.latest_for_clause(clause.id)
            tags = self.tag_repo.list_tags_for_clause(clause.id)
            result.append(
                ClauseWithLatestReview(
                    clause=ClauseOut.model_validate(clause),
                    latest_review=ReviewOut.model_validate(latest) if latest else None,
                    tags=[RiskTagOut.model_validate(t) for t in tags],
                )
            )
        return result

    def risk_dashboard(self, document_id: int, include_deprecated: bool = False) -> DocumentRiskDashboard:
        """文档风险看板。

        统计口径：
        - 未处理仅统计 process_status == open 的意见，resolved 不计入；
        - 废弃条款默认不参与统计，include_deprecated=True 时才纳入；
        - 标签是条款的风险分类，不作为意见状态参与流转统计。
        """
        doc = self.doc_service.get_or_404(document_id)
        all_clauses = self.clause_repo.list_by_document(document_id)
        clauses = [c for c in all_clauses if include_deprecated or not c.deprecated]

        risk_distribution = {level: 0 for level in RISK_LEVELS}
        status_distribution = {status: 0 for status in PROCESS_STATUSES}
        open_risk_distribution = {level: 0 for level in RISK_LEVELS}
        resolved_risk_distribution = {level: 0 for level in RISK_LEVELS}
        review_count = 0
        open_count = 0

        clause_max_risk: dict = {}  # clause_id -> 该条款意见中的最高风险等级
        tagged_clause_count = 0

        for clause in clauses:
            tags = self.tag_repo.list_tags_for_clause(clause.id)
            if tags:
                tagged_clause_count += 1
            for review in self.review_repo.list_by_clause(clause.id):
                review_count += 1
                risk_distribution[review.risk_level] += 1
                status_distribution[review.process_status] += 1
                if review.process_status == "open":
                    open_count += 1
                    open_risk_distribution[review.risk_level] += 1
                elif review.process_status == "resolved":
                    resolved_risk_distribution[review.risk_level] += 1
                current = clause_max_risk.get(clause.id)
                if current is None or RISK_ORDER[review.risk_level] > RISK_ORDER[current]:
                    clause_max_risk[clause.id] = review.risk_level

        highest_level: Optional[str] = None
        if clause_max_risk:
            highest_level = max(clause_max_risk.values(), key=lambda lv: RISK_ORDER[lv])

        highest_risk_clauses = [
            RiskClauseItem(clause_id=c.id, clause_no=c.clause_no, risk_level=clause_max_risk[c.id])
            for c in clauses
            if highest_level is not None and clause_max_risk.get(c.id) == highest_level
        ]
        untagged_high_risk_clauses = [
            RiskClauseItem(clause_id=c.id, clause_no=c.clause_no, risk_level=clause_max_risk[c.id])
            for c in clauses
            if clause_max_risk.get(c.id) in HIGH_RISK_LEVELS
            and not self.tag_repo.list_tags_for_clause(c.id)
        ]

        return DocumentRiskDashboard(
            document_id=doc.id,
            title=doc.title,
            version_no=doc.version_no,
            include_deprecated=include_deprecated,
            clause_count=len(clauses),
            deprecated_clause_count=sum(1 for c in all_clauses if c.deprecated),
            review_count=review_count,
            open_review_count=open_count,
            risk_distribution=risk_distribution,
            status_distribution=status_distribution,
            open_risk_distribution=open_risk_distribution,
            resolved_risk_distribution=resolved_risk_distribution,
            highest_risk_level=highest_level,
            highest_risk_clauses=highest_risk_clauses,
            tagged_clause_count=tagged_clause_count,
            untagged_high_risk_clauses=untagged_high_risk_clauses,
        )

"""审阅台账一致性自检。

对台账数据做只读审计，返回统一的 checks 数组：
每项包含 check_name / passed / issue_count / details。
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import PROCESS_STATUSES
from ..models import (
    Clause,
    ClauseTagBinding,
    Document,
    DocumentCopyMapping,
    ProcessRecord,
    Review,
)
from ..schemas import ConsistencyCheckItem, ConsistencyReport


def _item(check_name: str, details: List[dict]) -> ConsistencyCheckItem:
    return ConsistencyCheckItem(
        check_name=check_name,
        passed=len(details) == 0,
        issue_count=len(details),
        details=details,
    )


class ConsistencyService:
    def __init__(self, db: Session):
        self.db = db

    def run(self) -> ConsistencyReport:
        checks = [
            self._check_deprecated_clause_operations(),
            self._check_resolved_without_process_record(),
            self._check_duplicate_tag_bindings(),
            self._check_copy_mapping_integrity(),
            self._check_dashboard_consistency(),
            self._check_duplicate_clause_no(),
            self._check_open_list_purity(),
        ]
        failed = sum(1 for c in checks if not c.passed)
        return ConsistencyReport(
            overall_passed=failed == 0,
            check_count=len(checks),
            failed_count=failed,
            checks=checks,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def _check_deprecated_clause_operations(self) -> ConsistencyCheckItem:
        """废弃时间之后新增的意见/标签绑定/处理记录。"""
        details: List[dict] = []

        review_stmt = (
            select(Review, Clause)
            .join(Clause, Review.clause_id == Clause.id)
            .where(Clause.deprecated.is_(True), Clause.deprecated_at.isnot(None))
            .where(Review.created_at > Clause.deprecated_at)
        )
        for review, clause in self.db.execute(review_stmt).all():
            details.append({
                "kind": "review_after_deprecation",
                "review_id": review.id,
                "clause_id": clause.id,
                "created_at": review.created_at.isoformat() if review.created_at else None,
                "deprecated_at": clause.deprecated_at.isoformat(),
            })

        binding_stmt = (
            select(ClauseTagBinding, Clause)
            .join(Clause, ClauseTagBinding.clause_id == Clause.id)
            .where(Clause.deprecated.is_(True), Clause.deprecated_at.isnot(None))
            .where(ClauseTagBinding.created_at > Clause.deprecated_at)
        )
        for binding, clause in self.db.execute(binding_stmt).all():
            details.append({
                "kind": "tag_binding_after_deprecation",
                "binding_id": binding.id,
                "clause_id": clause.id,
                "tag_id": binding.tag_id,
            })

        record_stmt = (
            select(ProcessRecord, Clause)
            .join(Review, ProcessRecord.review_id == Review.id)
            .join(Clause, Review.clause_id == Clause.id)
            .where(Clause.deprecated.is_(True), Clause.deprecated_at.isnot(None))
            .where(ProcessRecord.created_at > Clause.deprecated_at)
        )
        for record, clause in self.db.execute(record_stmt).all():
            details.append({
                "kind": "process_record_after_deprecation",
                "record_id": record.id,
                "review_id": record.review_id,
                "clause_id": clause.id,
            })

        return _item("deprecated_clause_operations", details)

    def _check_resolved_without_process_record(self) -> ConsistencyCheckItem:
        """resolved 意见必须存在对应的处理记录。"""
        subq = (
            select(ProcessRecord.id)
            .where(ProcessRecord.review_id == Review.id, ProcessRecord.to_status == "resolved")
            .exists()
        )
        stmt = select(Review).where(Review.process_status == "resolved", ~subq)
        details = [
            {"review_id": r.id, "clause_id": r.clause_id, "reason": "resolved 意见缺少处理记录"}
            for r in self.db.scalars(stmt).all()
        ]
        return _item("resolved_reviews_missing_process_record", details)

    def _check_duplicate_tag_bindings(self) -> ConsistencyCheckItem:
        """同一条款重复绑定同一标签。"""
        stmt = (
            select(ClauseTagBinding.clause_id, ClauseTagBinding.tag_id, func.count())
            .group_by(ClauseTagBinding.clause_id, ClauseTagBinding.tag_id)
            .having(func.count() > 1)
        )
        details = [
            {"clause_id": c, "tag_id": t, "binding_count": n}
            for c, t, n in self.db.execute(stmt).all()
        ]
        return _item("duplicate_tag_bindings", details)

    def _check_copy_mapping_integrity(self) -> ConsistencyCheckItem:
        """复制映射的源/目标文档必须存在。"""
        details: List[dict] = []
        stmt = select(DocumentCopyMapping)
        for mapping in self.db.scalars(stmt).all():
            if self.db.get(Document, mapping.source_document_id) is None:
                details.append({
                    "mapping_id": mapping.id,
                    "missing": "source_document",
                    "document_id": mapping.source_document_id,
                })
            if self.db.get(Document, mapping.target_document_id) is None:
                details.append({
                    "mapping_id": mapping.id,
                    "missing": "target_document",
                    "document_id": mapping.target_document_id,
                })
        return _item("copy_mapping_integrity", details)

    def _check_dashboard_consistency(self) -> ConsistencyCheckItem:
        """看板聚合口径与明细数量比对（默认不含废弃条款）。"""
        details: List[dict] = []
        doc_ids = self.db.scalars(select(Document.id)).all()
        for doc_id in doc_ids:
            # 明细口径：直接统计未废弃条款下的意见
            base = (
                select(func.count())
                .select_from(Review)
                .join(Clause, Review.clause_id == Clause.id)
                .where(Clause.document_id == doc_id, Clause.deprecated.is_(False))
            )
            total = self.db.scalar(base) or 0
            open_count = self.db.scalar(base.where(Review.process_status == "open")) or 0
            resolved_count = self.db.scalar(base.where(Review.process_status == "resolved")) or 0
            # 看板口径：按 risk_distribution / status_distribution 汇总
            dash_total = self._dashboard_total(doc_id)
            if dash_total is not None and dash_total != (total, open_count, resolved_count):
                details.append({
                    "document_id": doc_id,
                    "detail_counts": {
                        "review_count": total,
                        "open_review_count": open_count,
                        "resolved_review_count": resolved_count,
                    },
                    "dashboard_counts": {
                        "review_count": dash_total[0],
                        "open_review_count": dash_total[1],
                        "resolved_review_count": dash_total[2],
                    },
                })
        return _item("dashboard_consistency", details)

    def _dashboard_total(self, document_id: int):
        from .dashboard_service import DashboardService

        dash = DashboardService(self.db).risk_dashboard(document_id)
        resolved = sum(dash.resolved_risk_distribution.values())
        return (dash.review_count, dash.open_review_count, resolved)

    def _check_duplicate_clause_no(self) -> ConsistencyCheckItem:
        """同一文档下 clause_no 不允许重复。"""
        stmt = (
            select(Clause.document_id, Clause.clause_no, func.count())
            .group_by(Clause.document_id, Clause.clause_no)
            .having(func.count() > 1)
        )
        details = [
            {"document_id": d, "clause_no": no, "count": n}
            for d, no, n in self.db.execute(stmt).all()
        ]
        return _item("duplicate_clause_no", details)

    def _check_open_list_purity(self) -> ConsistencyCheckItem:
        """未处理列表只允许 open 状态；resolved/rejected 不得混入，
        process_status 必须是首轮定义的枚举值。"""
        details: List[dict] = []
        # 非法状态值
        stmt = select(Review).where(Review.process_status.notin_(PROCESS_STATUSES))
        for r in self.db.scalars(stmt).all():
            details.append({
                "review_id": r.id,
                "clause_id": r.clause_id,
                "process_status": r.process_status,
                "reason": "非法 process_status 取值",
            })
        # 未处理列表（按风险等级查询 open）中混入 resolved/rejected
        for level in ("low", "medium", "high", "critical"):
            open_stmt = select(Review).where(
                Review.risk_level == level, Review.process_status == "open"
            )
            for r in self.db.scalars(open_stmt).all():
                if r.process_status != "open":
                    details.append({
                        "review_id": r.id,
                        "clause_id": r.clause_id,
                        "process_status": r.process_status,
                        "reason": "resolved/rejected 意见混入未处理列表",
                    })
        return _item("open_list_purity", details)

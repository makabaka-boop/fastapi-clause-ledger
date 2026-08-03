from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import (
    RiskLevel,
    TERMINAL_PROCESS_STATUSES,
)
from app.models.clause import Clause
from app.models.comment import Comment
from app.models.copy_mapping import CopyMapping, ClauseCopyMapping
from app.models.document import Document
from app.models.process_record import ProcessRecord
from app.models.tag_binding import TagBinding


class ConsistencyService:
    def __init__(self, db: Session):
        self.db = db

    def run_all_checks(self) -> Dict:
        checks = [
            self._check_comments_on_deprecated_clauses(),
            self._check_resolved_comments_missing_records(),
            self._check_duplicate_tag_bindings(),
            self._check_missing_copy_mappings(),
            self._check_dashboard_stats_consistency(),
            self._check_duplicate_clause_no(),
            self._check_terminal_comments_in_unresolved(),
        ]

        failed = sum(1 for c in checks if not c["passed"])
        return {
            "all_passed": failed == 0,
            "total_checks": len(checks),
            "failed_checks": failed,
            "checks": checks,
        }

    def _make_check(self, name: str, issues: List[Dict]) -> Dict:
        return {
            "check_name": name,
            "passed": len(issues) == 0,
            "issue_count": len(issues),
            "details": issues,
        }

    def _check_comments_on_deprecated_clauses(self) -> Dict:
        rows = self.db.execute(
            select(Comment.id, Comment.clause_id)
            .join(Clause, Clause.id == Comment.clause_id)
            .where(Clause.deprecated.is_(True))
        ).all()
        issues = [
            {"comment_id": r.id, "clause_id": r.clause_id}
            for r in rows
        ]
        return self._make_check("comments_on_deprecated_clauses", issues)

    def _check_resolved_comments_missing_records(self) -> Dict:
        resolved_comments = self.db.execute(
            select(Comment.id).where(
                Comment.process_status == "resolved"
            )
        ).scalars().all()

        if not resolved_comments:
            return self._make_check(
                "resolved_comments_missing_records", []
            )

        recorded_rows = self.db.execute(
            select(ProcessRecord.comment_id).where(
                ProcessRecord.comment_id.in_(resolved_comments),
                ProcessRecord.to_status == "resolved",
            )
        ).scalars().all()
        recorded_ids = set(recorded_rows)

        issues = [
            {"comment_id": cid}
            for cid in resolved_comments
            if cid not in recorded_ids
        ]
        return self._make_check(
            "resolved_comments_missing_records", issues
        )

    def _check_duplicate_tag_bindings(self) -> Dict:
        rows = self.db.execute(
            select(
                TagBinding.clause_id,
                TagBinding.tag_id,
                func.count(TagBinding.id).label("cnt"),
            )
            .group_by(TagBinding.clause_id, TagBinding.tag_id)
            .having(func.count(TagBinding.id) > 1)
        ).all()
        issues = [
            {
                "clause_id": r.clause_id,
                "tag_id": r.tag_id,
                "count": r.cnt,
            }
            for r in rows
        ]
        return self._make_check("duplicate_tag_bindings", issues)

    def _check_missing_copy_mappings(self) -> Dict:
        issues = []

        mappings = self.db.execute(select(CopyMapping)).scalars().all()
        doc_ids = set(
            self.db.execute(select(Document.id)).scalars().all()
        )
        for m in mappings:
            if m.source_document_id not in doc_ids:
                issues.append(
                    {
                        "type": "missing_source_document",
                        "copy_mapping_id": m.id,
                        "source_document_id": m.source_document_id,
                    }
                )
            if m.target_document_id not in doc_ids:
                issues.append(
                    {
                        "type": "missing_target_document",
                        "copy_mapping_id": m.id,
                        "target_document_id": m.target_document_id,
                    }
                )

        clause_ids = set(
            self.db.execute(select(Clause.id)).scalars().all()
        )
        clause_mappings = self.db.execute(
            select(ClauseCopyMapping)
        ).scalars().all()
        for cm in clause_mappings:
            if cm.source_clause_id not in clause_ids:
                issues.append(
                    {
                        "type": "missing_source_clause",
                        "clause_copy_mapping_id": cm.id,
                        "source_clause_id": cm.source_clause_id,
                    }
                )
            if cm.target_clause_id not in clause_ids:
                issues.append(
                    {
                        "type": "missing_target_clause",
                        "clause_copy_mapping_id": cm.id,
                        "target_clause_id": cm.target_clause_id,
                    }
                )

        for m in mappings:
            target_clauses = self.db.execute(
                select(Clause.id).where(
                    Clause.document_id == m.target_document_id
                )
            ).scalars().all()
            mapped_targets = {
                cm.target_clause_id
                for cm in clause_mappings
                if cm.copy_mapping_id == m.id
            }
            for tcid in target_clauses:
                if tcid not in mapped_targets:
                    issues.append(
                        {
                            "type": "unmapped_target_clause",
                            "copy_mapping_id": m.id,
                            "target_clause_id": tcid,
                        }
                    )

        return self._make_check("missing_copy_mappings", issues)

    def _check_dashboard_stats_consistency(self) -> Dict:
        issues = []
        documents = self.db.execute(select(Document.id)).scalars().all()

        for doc_id in documents:
            clause_ids = self.db.execute(
                select(Clause.id).where(
                    Clause.document_id == doc_id,
                    Clause.deprecated.is_(False),
                )
            ).scalars().all()

            expected_unresolved = {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            }
            expected_resolved = 0

            if clause_ids:
                comments = self.db.execute(
                    select(Comment).where(
                        Comment.clause_id.in_(clause_ids)
                    )
                ).scalars().all()
                for c in comments:
                    if c.process_status == "resolved":
                        expected_resolved += 1
                    elif c.process_status not in TERMINAL_PROCESS_STATUSES:
                        expected_unresolved[c.risk_level] = (
                            expected_unresolved.get(c.risk_level, 0) + 1
                        )

            actual_total = sum(expected_unresolved.values())

            for level in ("low", "medium", "high", "critical"):
                count = self.db.execute(
                    select(func.count(Comment.id))
                    .join(Clause, Clause.id == Comment.clause_id)
                    .where(
                        Clause.document_id == doc_id,
                        Clause.deprecated.is_(False),
                        Comment.risk_level == level,
                        Comment.process_status.notin_(
                            list(TERMINAL_PROCESS_STATUSES)
                        ),
                    )
                ).scalar_one()
                if count != expected_unresolved[level]:
                    issues.append(
                        {
                            "document_id": doc_id,
                            "risk_level": level,
                            "expected": expected_unresolved[level],
                            "actual": count,
                        }
                    )

        return self._make_check("dashboard_stats_consistency", issues)

    def _check_duplicate_clause_no(self) -> Dict:
        rows = self.db.execute(
            select(
                Clause.document_id,
                Clause.clause_no,
                func.count(Clause.id).label("cnt"),
            )
            .group_by(Clause.document_id, Clause.clause_no)
            .having(func.count(Clause.id) > 1)
        ).all()
        issues = [
            {
                "document_id": r.document_id,
                "clause_no": r.clause_no,
                "count": r.cnt,
            }
            for r in rows
        ]
        return self._make_check("duplicate_clause_no", issues)

    def _check_terminal_comments_in_unresolved(self) -> Dict:
        issues = []
        for level in (rl.value for rl in RiskLevel):
            rows = self.db.execute(
                select(Comment.id, Comment.process_status)
                .where(
                    Comment.risk_level == level,
                    Comment.process_status.notin_(
                        list(TERMINAL_PROCESS_STATUSES)
                    ),
                )
            ).all()
            for r in rows:
                if r.process_status in TERMINAL_PROCESS_STATUSES:
                    issues.append(
                        {
                            "comment_id": r.id,
                            "process_status": r.process_status,
                            "risk_level": level,
                        }
                    )
        return self._make_check(
            "terminal_comments_in_unresolved", issues
        )

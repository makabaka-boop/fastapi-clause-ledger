from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.enums import ProcessStatus, RiskLevel
from app.repositories import (
    ClauseRepository,
    CommentRepository,
    DocumentCopyRepository,
    DocumentRepository,
    ProcessingRecordRepository,
    TagBindingRepository,
)

UNRESOLVED_STATUSES = {ProcessStatus.OPEN.value, ProcessStatus.ACCEPTED.value}
RESOLVED_STATUSES = {ProcessStatus.REJECTED.value, ProcessStatus.RESOLVED.value}
MANDATORY_RECORD_FINAL_STATUSES = {ProcessStatus.RESOLVED.value}


class ConsistencyService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentRepository(db)
        self.clauses = ClauseRepository(db)
        self.comments = CommentRepository(db)
        self.bindings = TagBindingRepository(db)
        self.records = ProcessingRecordRepository(db)
        self.copies = DocumentCopyRepository(db)

    def _check(self, name: str, issues: list[schemas.ConsistencyIssue]) -> schemas.ConsistencyCheck:
        return schemas.ConsistencyCheck(
            name=name,
            passed=len(issues) == 0,
            issue_count=len(issues),
            issues=issues,
        )

    def _check_deprecated_clause_comments(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        stmt = (
            select(models.Comment)
            .join(models.Clause, models.Comment.clause_id == models.Clause.id)
            .where(models.Clause.deprecated.is_(True))
        )
        for comment in self.db.execute(stmt).scalars().all():
            issues.append(
                schemas.ConsistencyIssue(
                    entity="comment",
                    entity_id=comment.id,
                    message="Comment exists on a deprecated clause",
                    details={
                        "clause_id": comment.clause_id,
                        "reviewer_name": comment.reviewer_name,
                    },
                )
            )
        return self._check("comments_on_deprecated_clauses", issues)

    def _check_resolved_comments_missing_records(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        stmt = select(models.Comment).where(
            models.Comment.process_status.in_(MANDATORY_RECORD_FINAL_STATUSES)
        )
        for comment in self.db.execute(stmt).scalars().all():
            records = self.records.list_by_comment(comment.id)
            has_resolution = any(r.to_status == ProcessStatus.RESOLVED.value for r in records)
            if not has_resolution:
                issues.append(
                    schemas.ConsistencyIssue(
                        entity="comment",
                        entity_id=comment.id,
                        message="Resolved comment is missing a processing record",
                        details={
                            "clause_id": comment.clause_id,
                            "process_status": comment.process_status,
                        },
                    )
                )
        return self._check("resolved_comments_missing_processing_records", issues)

    def _check_duplicate_tag_bindings(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        stmt = (
            select(
                models.TagBinding.clause_id,
                models.TagBinding.tag_id,
                func.count(models.TagBinding.id).label("cnt"),
            )
            .group_by(models.TagBinding.clause_id, models.TagBinding.tag_id)
            .having(func.count(models.TagBinding.id) > 1)
        )
        for clause_id, tag_id, cnt in self.db.execute(stmt).all():
            issues.append(
                schemas.ConsistencyIssue(
                    entity="tag_binding",
                    entity_id=clause_id,
                    message="Duplicate tag binding detected for clause",
                    details={"clause_id": clause_id, "tag_id": tag_id, "count": cnt},
                )
            )
        return self._check("duplicate_tag_bindings", issues)

    def _check_copy_mappings(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        for mapping in self.copies.list_all():
            source = self.documents.get_by_id(mapping.source_document_id)
            target = self.documents.get_by_id(mapping.target_document_id)
            if source is None or target is None:
                issues.append(
                    schemas.ConsistencyIssue(
                        entity="document_copy",
                        entity_id=mapping.id,
                        message="Document copy mapping references a missing document",
                        details={
                            "source_document_id": mapping.source_document_id,
                            "target_document_id": mapping.target_document_id,
                            "source_exists": source is not None,
                            "target_exists": target is not None,
                        },
                    )
                )
        return self._check("document_copy_mappings", issues)

    def _check_dashboard_consistency(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        status_counts_stmt = select(
            models.Clause.document_id,
            models.Comment.process_status,
            func.count(models.Comment.id),
        ).join(
            models.Clause, models.Comment.clause_id == models.Clause.id
        ).group_by(models.Clause.document_id, models.Comment.process_status)

        counts: dict[int, Counter] = {}
        for document_id, status, cnt in self.db.execute(status_counts_stmt).all():
            counts.setdefault(document_id, Counter())[status] = cnt

        for doc in self.documents.list_all():
            doc_counts = counts.get(doc.id, Counter())
            total = sum(doc_counts.values())
            status_sum = sum(
                doc_counts.get(s, 0)
                for s in (
                    ProcessStatus.OPEN.value,
                    ProcessStatus.ACCEPTED.value,
                    ProcessStatus.REJECTED.value,
                    ProcessStatus.RESOLVED.value,
                )
            )
            if total != status_sum:
                issues.append(
                    schemas.ConsistencyIssue(
                        entity="document",
                        entity_id=doc.id,
                        message="Dashboard comment counts do not match status detail counts",
                        details={"total_comments": total, "status_sum": status_sum},
                    )
                )
        return self._check("dashboard_statistics_consistency", issues)

    def _check_duplicate_clause_no(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        stmt = (
            select(
                models.Clause.document_id,
                models.Clause.clause_no,
                func.count(models.Clause.id).label("cnt"),
            )
            .where(models.Clause.deprecated.is_(False))
            .group_by(models.Clause.document_id, models.Clause.clause_no)
            .having(func.count(models.Clause.id) > 1)
        )
        for document_id, clause_no, cnt in self.db.execute(stmt).all():
            issues.append(
                schemas.ConsistencyIssue(
                    entity="clause",
                    entity_id=document_id,
                    message="Duplicate clause_no found within document",
                    details={
                        "document_id": document_id,
                        "clause_no": clause_no,
                        "count": cnt,
                    },
                )
            )
        return self._check("duplicate_clause_no_within_document", issues)

    def _check_unresolved_list_status(self) -> schemas.ConsistencyCheck:
        issues: list[schemas.ConsistencyIssue] = []
        for level in RiskLevel:
            for comment in self.comments.list_unresolved_by_risk_level(level.value):
                if comment.process_status in RESOLVED_STATUSES:
                    issues.append(
                        schemas.ConsistencyIssue(
                            entity="comment",
                            entity_id=comment.id,
                            message="rejected/resolved comment appears in unresolved results",
                            details={
                                "clause_id": comment.clause_id,
                                "process_status": comment.process_status,
                                "risk_level": level.value,
                            },
                        )
                    )
        return self._check("unresolved_list_status_consistency", issues)

    def run_checks(self) -> schemas.ConsistencyReport:
        checks = [
            self._check_deprecated_clause_comments(),
            self._check_resolved_comments_missing_records(),
            self._check_duplicate_tag_bindings(),
            self._check_copy_mappings(),
            self._check_dashboard_consistency(),
            self._check_duplicate_clause_no(),
            self._check_unresolved_list_status(),
        ]
        total_issues = sum(c.issue_count for c in checks)
        passed_checks = sum(1 for c in checks if c.passed)
        return schemas.ConsistencyReport(
            passed=total_issues == 0,
            total_checks=len(checks),
            passed_checks=passed_checks,
            failed_checks=len(checks) - passed_checks,
            total_issues=total_issues,
            checked_at=datetime.now(timezone.utc),
            checks=checks,
        )

from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import (
    ProcessStatus,
    RiskLevel,
    TERMINAL_PROCESS_STATUSES,
)
from app.exceptions.app_exceptions import NotFoundError
from app.models.clause import Clause
from app.models.comment import Comment
from app.models.tag import Tag
from app.models.tag_binding import TagBinding
from app.repositories.document_repo import DocumentRepository


RISK_ORDER = {
    RiskLevel.LOW.value: 0,
    RiskLevel.MEDIUM.value: 1,
    RiskLevel.HIGH.value: 2,
    RiskLevel.CRITICAL.value: 3,
}


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.document_repo = DocumentRepository(db)

    def document_dashboard(self, document_id: int) -> Dict:
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )

        total_clauses = self.db.execute(
            select(func.count(Clause.id)).where(
                Clause.document_id == document_id
            )
        ).scalar_one()

        deprecated_clauses = self.db.execute(
            select(func.count(Clause.id)).where(
                Clause.document_id == document_id,
                Clause.deprecated.is_(True),
            )
        ).scalar_one()

        active_clauses = total_clauses - deprecated_clauses

        comments = self.db.execute(
            select(Comment).join(Clause, Clause.id == Comment.clause_id).where(
                Clause.document_id == document_id
            )
        ).scalars().all()

        total_comments = len(comments)
        open_comments = sum(
            1
            for c in comments
            if c.process_status not in TERMINAL_PROCESS_STATUSES
        )

        risk_by_level = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
            "total": total_comments,
        }
        status_by_process = {
            "open": 0,
            "accepted": 0,
            "rejected": 0,
            "resolved": 0,
        }

        for c in comments:
            risk_by_level[c.risk_level] = risk_by_level.get(c.risk_level, 0) + 1
            status_by_process[c.process_status] = (
                status_by_process.get(c.process_status, 0) + 1
            )

        tag_distribution_stmt = (
            select(
                Tag.id.label("tag_id"),
                Tag.name.label("tag_name"),
                Comment.risk_level.label("risk_level"),
                func.count(Comment.id).label("cnt"),
            )
            .join(TagBinding, TagBinding.tag_id == Tag.id)
            .join(Clause, Clause.id == TagBinding.clause_id)
            .outerjoin(Comment, Comment.clause_id == Clause.id)
            .where(Clause.document_id == document_id)
            .group_by(Tag.id, Tag.name, Comment.risk_level)
            .order_by(Tag.id)
        )
        rows = self.db.execute(tag_distribution_stmt).all()

        tag_dist: Dict[int, Dict] = {}
        for row in rows:
            tid = row.tag_id
            if tid not in tag_dist:
                tag_dist[tid] = {
                    "tag_id": tid,
                    "tag_name": row.tag_name,
                    "low": 0,
                    "medium": 0,
                    "high": 0,
                    "critical": 0,
                    "total": 0,
                }
            if row.risk_level is not None:
                tag_dist[tid][row.risk_level] = row.cnt or 0

        tag_distribution = []
        for item in tag_dist.values():
            item["total"] = (
                item["low"] + item["medium"] + item["high"] + item["critical"]
            )
            tag_distribution.append(item)

        return {
            "document_id": document_id,
            "total_clauses": total_clauses,
            "deprecated_clauses": deprecated_clauses,
            "active_clauses": active_clauses,
            "total_comments": total_comments,
            "open_comments": open_comments,
            "risk_by_level": risk_by_level,
            "status_by_process": status_by_process,
            "tag_distribution": tag_distribution,
        }

    def risk_dashboard(
        self, document_id: int, include_deprecated: bool = False
    ) -> Dict:
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )

        clause_stmt = select(Clause).where(Clause.document_id == document_id)
        if not include_deprecated:
            clause_stmt = clause_stmt.where(Clause.deprecated.is_(False))
        clauses = list(self.db.execute(clause_stmt).scalars().all())
        clause_ids = [c.id for c in clauses]
        clause_by_id = {c.id: c for c in clauses}

        unresolved_by_risk = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
            "total": 0,
        }
        resolved_count = 0

        clause_unresolved: Dict[int, List[Comment]] = {cid: [] for cid in clause_ids}
        clause_latest: Dict[int, Comment] = {}

        if clause_ids:
            comments = list(
                self.db.execute(
                    select(Comment)
                    .where(Comment.clause_id.in_(clause_ids))
                    .order_by(Comment.clause_id, Comment.created_at, Comment.id)
                ).scalars().all()
            )
            for c in comments:
                if c.process_status == ProcessStatus.RESOLVED.value:
                    resolved_count += 1
                if c.process_status not in TERMINAL_PROCESS_STATUSES:
                    unresolved_by_risk[c.risk_level] = (
                        unresolved_by_risk.get(c.risk_level, 0) + 1
                    )
                    unresolved_by_risk["total"] += 1
                    clause_unresolved.setdefault(c.clause_id, []).append(c)
                existing = clause_latest.get(c.clause_id)
                if existing is None or c.created_at >= existing.created_at:
                    clause_latest[c.clause_id] = c

        tagged_clause_ids = set()
        if clause_ids:
            binding_rows = self.db.execute(
                select(TagBinding.clause_id)
                .where(TagBinding.clause_id.in_(clause_ids))
                .distinct()
            ).all()
            tagged_clause_ids = {row[0] for row in binding_rows}

        clause_summaries: List[Dict] = []
        for cid in clause_ids:
            unresolved = clause_unresolved.get(cid, [])
            if unresolved:
                highest = max(
                    unresolved, key=lambda x: RISK_ORDER.get(x.risk_level, -1)
                )
                highest_risk = highest.risk_level
            else:
                highest_risk = None

            latest = clause_latest.get(cid)
            clause_summaries.append(
                {
                    "clause_id": cid,
                    "clause_no": clause_by_id[cid].clause_no,
                    "clause_type": clause_by_id[cid].clause_type,
                    "importance": clause_by_id[cid].importance,
                    "highest_risk_level": highest_risk,
                    "unresolved_comment_count": len(unresolved),
                    "latest_comment_text": latest.comment_text if latest else None,
                    "_has_tags": cid in tagged_clause_ids,
                }
            )

        risk_ranked = [
            s for s in clause_summaries if s["highest_risk_level"] is not None
        ]
        risk_ranked.sort(
            key=lambda s: (
                -RISK_ORDER.get(s["highest_risk_level"], -1),
                -s["unresolved_comment_count"],
                s["clause_no"],
            )
        )
        highest_risk_clauses = [
            {k: v for k, v in s.items() if not k.startswith("_")}
            for s in risk_ranked
        ]

        untagged_high_risk = [
            {k: v for k, v in s.items() if not k.startswith("_")}
            for s in risk_ranked
            if not s["_has_tags"]
            and RISK_ORDER.get(s["highest_risk_level"], -1)
            >= RISK_ORDER[RiskLevel.HIGH.value]
        ]

        return {
            "document_id": document_id,
            "include_deprecated": include_deprecated,
            "unresolved_by_risk": unresolved_by_risk,
            "resolved_count": resolved_count,
            "highest_risk_clauses": highest_risk_clauses,
            "tagged_clause_count": len(tagged_clause_ids),
            "untagged_high_risk_clauses": untagged_high_risk,
        }

"""Service layer: business rules and orchestration.

Each function opens a transaction, applies domain rules that live above the
storage layer, and returns plain dicts. Guard rails enforced here:

  * a document's clause_no values are unique (delegated to the repo UNIQUE)
  * deprecated clauses reject new reviews and new tag bindings
  * review status changes follow the state machine, and the transitions
    open->accepted/rejected and accepted->resolved must write a process record
  * copying a document duplicates only non-deprecated clauses plus their tag
    bindings, and never copies resolved reviews (in fact no reviews are copied)
"""

from __future__ import annotations

from .database import transaction
from .enums import ImportMode, ProcessStatus, RiskLevel
from .exceptions import RuleViolationError, ValidationError
from .repositories import (
    ClauseRepository,
    ClauseTagRepository,
    ConsistencyRepository,
    CopyClauseMapRepository,
    DocumentCopyRepository,
    DocumentRepository,
    ProcessRecordRepository,
    ReviewRepository,
    RiskTagRepository,
)
from .state_machine import assert_transition, requires_record
from .utils import now_iso


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
def create_document(payload) -> dict:
    with transaction() as conn:
        return DocumentRepository.create(
            conn,
            title=payload.title,
            source_department=payload.source_department,
            version_no=payload.version_no,
            document_status=payload.document_status.value,
        )


def update_document_status(document_id: int, payload) -> dict:
    with transaction() as conn:
        return DocumentRepository.update_status(
            conn, document_id, payload.document_status.value
        )


def get_document(document_id: int) -> dict:
    with transaction() as conn:
        return DocumentRepository.get(conn, document_id)


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
def add_clauses(document_id: int, payload) -> list[dict]:
    """Batch create. Duplicate clause_no (within request or existing) fails."""
    with transaction() as conn:
        DocumentRepository.get(conn, document_id)  # 404 if missing

        seen: set[str] = set()
        for clause in payload.clauses:
            if clause.clause_no in seen:
                raise ValidationError(
                    f"Duplicate clause_no '{clause.clause_no}' in request payload.",
                    details={"clause_no": clause.clause_no},
                )
            seen.add(clause.clause_no)

        created = []
        for clause in payload.clauses:
            created.append(
                ClauseRepository.create(
                    conn,
                    document_id=document_id,
                    clause_no=clause.clause_no,
                    clause_text=clause.clause_text,
                    clause_type=clause.clause_type.value,
                    importance=clause.importance.value,
                )
            )
        return created


def import_clauses(document_id: int, payload) -> dict:
    """Idempotent import.

    ``skip_existing``   : keep existing clause_no untouched, insert new ones.
    ``update_existing`` : overwrite content of existing clause_no, insert new.
    """
    with transaction() as conn:
        DocumentRepository.get(conn, document_id)

        seen: set[str] = set()
        for clause in payload.clauses:
            if clause.clause_no in seen:
                raise ValidationError(
                    f"Duplicate clause_no '{clause.clause_no}' in import payload.",
                    details={"clause_no": clause.clause_no},
                )
            seen.add(clause.clause_no)

        created, updated, skipped = [], [], []
        mapping = []
        for clause in payload.clauses:
            existing = ClauseRepository.get_by_no(conn, document_id, clause.clause_no)
            if existing is None:
                new_clause = ClauseRepository.create(
                    conn,
                    document_id=document_id,
                    clause_no=clause.clause_no,
                    clause_text=clause.clause_text,
                    clause_type=clause.clause_type.value,
                    importance=clause.importance.value,
                )
                created.append(new_clause)
                mapping.append({
                    "clause_no": clause.clause_no,
                    "action": "created",
                    "previous_clause_id": None,
                    "final_clause_id": new_clause["id"],
                })
            elif payload.mode == ImportMode.update_existing:
                # The row is reused, so old and final ids are identical; this
                # lets callers resolve any reference held before the import.
                refreshed = ClauseRepository.update_content(
                    conn,
                    existing["id"],
                    clause_text=clause.clause_text,
                    clause_type=clause.clause_type.value,
                    importance=clause.importance.value,
                )
                updated.append(refreshed)
                mapping.append({
                    "clause_no": clause.clause_no,
                    "action": "updated",
                    "previous_clause_id": existing["id"],
                    "final_clause_id": refreshed["id"],
                })
            else:  # skip_existing — leave the stored row untouched
                skipped.append(clause.clause_no)
                mapping.append({
                    "clause_no": clause.clause_no,
                    "action": "skipped",
                    "previous_clause_id": existing["id"],
                    "final_clause_id": existing["id"],
                })

        return {
            "mode": payload.mode.value,
            "created_count": len(created),
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "mapping": mapping,
        }


def deprecate_clause(clause_id: int) -> dict:
    with transaction() as conn:
        return ClauseRepository.set_deprecated(conn, clause_id, True)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
def _assert_not_frozen_by_deprecation(conn, review, current) -> None:
    """Block status changes on unprocessed opinions of deprecated clauses.

    Once a clause is deprecated, any opinion still in ``open`` is frozen: it can
    no longer be moved to accepted/rejected. Opinions that were already being
    handled (accepted) keep their normal transitions so in-flight work can be
    finished, and reading history is never affected.
    """
    if current != ProcessStatus.open:
        return
    clause = ClauseRepository.get(conn, review["clause_id"])
    if clause["deprecated"]:
        raise RuleViolationError(
            "Cannot change the status of an unprocessed opinion on a "
            "deprecated clause.",
            details={
                "clause_id": clause["id"],
                "review_id": review["id"],
                "process_status": current.value,
            },
        )


def add_review(clause_id: int, payload) -> dict:
    with transaction() as conn:
        clause = ClauseRepository.get(conn, clause_id)
        if clause["deprecated"]:
            raise RuleViolationError(
                "Cannot add a review to a deprecated clause.",
                details={"clause_id": clause_id},
            )
        return ReviewRepository.create(
            conn,
            clause_id=clause_id,
            reviewer_name=payload.reviewer_name,
            comment_text=payload.comment_text,
            risk_level=payload.risk_level.value,
        )


def change_review_status(review_id: int, payload) -> dict:
    """Move a review through the state machine.

    Transitions that require a process record (open->accepted/rejected,
    accepted->resolved) are written atomically together with the status change.
    """
    with transaction() as conn:
        review = ReviewRepository.get(conn, review_id)
        current = ProcessStatus(review["process_status"])
        target = payload.to_status

        # A deprecated clause is frozen for unprocessed opinions: history stays
        # readable, but an 'open' opinion can no longer be advanced.
        _assert_not_frozen_by_deprecation(conn, review, current)

        assert_transition(current, target)

        if requires_record(current, target):
            if not payload.operator:
                raise ValidationError(
                    "This status change requires an 'operator' for the process record.",
                    details={
                        "from_status": current.value,
                        "to_status": target.value,
                    },
                )
            ProcessRecordRepository.create(
                conn,
                review_id=review_id,
                from_status=current.value,
                to_status=target.value,
                operator=payload.operator,
                note=payload.note,
            )

        return ReviewRepository.update_status(conn, review_id, target.value)


# ---------------------------------------------------------------------------
# Process records
# ---------------------------------------------------------------------------
def add_process_record(review_id: int, payload) -> dict:
    """Explicitly journal a handling record for a review.

    The recorded ``from_status`` must match the review's current status and the
    transition must be legal; the review is advanced to ``to_status``.
    """
    with transaction() as conn:
        review = ReviewRepository.get(conn, review_id)
        current = ProcessStatus(review["process_status"])

        if payload.from_status != current:
            raise ValidationError(
                "from_status does not match the review's current status.",
                details={
                    "expected_from_status": current.value,
                    "given_from_status": payload.from_status.value,
                },
            )
        _assert_not_frozen_by_deprecation(conn, review, current)
        assert_transition(current, payload.to_status)

        record = ProcessRecordRepository.create(
            conn,
            review_id=review_id,
            from_status=payload.from_status.value,
            to_status=payload.to_status.value,
            operator=payload.operator,
            note=payload.note,
        )
        ReviewRepository.update_status(conn, review_id, payload.to_status.value)
        return record


def get_process_history(review_id: int) -> list[dict]:
    with transaction() as conn:
        ReviewRepository.get(conn, review_id)  # 404 if missing
        return ProcessRecordRepository.list_for_review(conn, review_id)


# ---------------------------------------------------------------------------
# Risk tags & bindings
# ---------------------------------------------------------------------------
def create_risk_tag(payload) -> dict:
    with transaction() as conn:
        return RiskTagRepository.create(
            conn, name=payload.name, description=payload.description
        )


def bind_tag(clause_id: int, payload) -> dict:
    with transaction() as conn:
        clause = ClauseRepository.get(conn, clause_id)
        if clause["deprecated"]:
            raise RuleViolationError(
                "Cannot bind a new tag to a deprecated clause.",
                details={"clause_id": clause_id},
            )
        RiskTagRepository.get(conn, payload.tag_id)  # 404 if missing
        return ClauseTagRepository.bind(conn, clause_id, payload.tag_id)


# ---------------------------------------------------------------------------
# Reporting / composite views
# ---------------------------------------------------------------------------
def list_clauses_with_latest_review(document_id: int) -> list[dict]:
    with transaction() as conn:
        DocumentRepository.get(conn, document_id)
        result = []
        for clause in ClauseRepository.list_for_document(conn, document_id):
            latest = ReviewRepository.latest_for_clause(conn, clause["id"])
            result.append({"clause": clause, "latest_review": latest})
        return result


def list_unprocessed_by_risk(risk_level: RiskLevel) -> list[dict]:
    with transaction() as conn:
        return ReviewRepository.list_unprocessed_by_risk(conn, risk_level.value)


def tag_risk_distribution(tag_id: int) -> dict:
    """Distribution of review risk levels across clauses carrying a tag."""
    with transaction() as conn:
        tag = RiskTagRepository.get(conn, tag_id)
        rows = conn.execute(
            """SELECT r.risk_level AS risk_level, COUNT(*) AS count
               FROM reviews r
               JOIN clause_tags ct ON ct.clause_id = r.clause_id
               WHERE ct.tag_id = ?
               GROUP BY r.risk_level""",
            (tag_id,),
        ).fetchall()
        distribution = [
            {"risk_level": row["risk_level"], "count": row["count"]} for row in rows
        ]
        total = sum(item["count"] for item in distribution)
        return {
            "tag_id": tag["id"],
            "tag_name": tag["name"],
            "total_reviews": total,
            "distribution": distribution,
        }


def risk_dashboard(document_id: int) -> dict:
    with transaction() as conn:
        doc = DocumentRepository.get(conn, document_id)
        clauses = ClauseRepository.list_for_document(conn, document_id)
        clause_ids = [c["id"] for c in clauses]
        active = sum(1 for c in clauses if not c["deprecated"])
        deprecated = len(clauses) - active

        risk_dist, proc_dist, total_reviews, open_reviews = [], [], 0, 0
        if clause_ids:
            placeholders = ",".join("?" for _ in clause_ids)
            risk_rows = conn.execute(
                f"""SELECT risk_level, COUNT(*) AS count FROM reviews
                    WHERE clause_id IN ({placeholders})
                    GROUP BY risk_level""",
                clause_ids,
            ).fetchall()
            risk_dist = [
                {"risk_level": r["risk_level"], "count": r["count"]} for r in risk_rows
            ]
            proc_rows = conn.execute(
                f"""SELECT process_status, COUNT(*) AS count FROM reviews
                    WHERE clause_id IN ({placeholders})
                    GROUP BY process_status""",
                clause_ids,
            ).fetchall()
            proc_dist = [
                {"process_status": r["process_status"], "count": r["count"]}
                for r in proc_rows
            ]
            total_reviews = sum(item["count"] for item in risk_dist)
            open_reviews = sum(
                item["count"]
                for item in proc_dist
                if item["process_status"] == ProcessStatus.open.value
            )

        return {
            "document_id": doc["id"],
            "document_title": doc["title"],
            "total_clauses": len(clauses),
            "active_clauses": active,
            "deprecated_clauses": deprecated,
            "total_reviews": total_reviews,
            "open_reviews": open_reviews,
            "risk_distribution": risk_dist,
            "process_distribution": proc_dist,
        }


# Ranking of risk levels, lowest -> highest, for "highest risk" computations.
_RISK_ORDER = {
    RiskLevel.low: 0,
    RiskLevel.medium: 1,
    RiskLevel.high: 2,
    RiskLevel.critical: 3,
}
_HIGH_RISK = {RiskLevel.high, RiskLevel.critical}


def risk_board(document_id: int, include_deprecated: bool = False) -> dict:
    """Risk board showing inheritance and handling progress for a document.

    Counting rules:
      * ``unprocessed_count`` counts only ``open`` opinions — resolved (and any
        other non-open) opinions never appear in the unprocessed tally;
      * ``resolved_count`` counts ``resolved`` opinions;
      * deprecated clauses are excluded unless ``include_deprecated`` is true;
      * tags are clause-level risk classifications (from clause_tags), reused
        exactly as bound — they are not derived from opinion status.
    """
    with transaction() as conn:
        doc = DocumentRepository.get(conn, document_id)
        clauses = [
            c for c in ClauseRepository.list_for_document(conn, document_id)
            if include_deprecated or not c["deprecated"]
        ]

        # Per-risk-level unprocessed (open) and resolved tallies.
        breakdown = {
            level: {"unprocessed_count": 0, "resolved_count": 0}
            for level in RiskLevel
        }
        tagged_clause_count = 0
        top_risk_clauses = []
        untagged_high_risk = []

        for clause in clauses:
            reviews = conn.execute(
                "SELECT risk_level, process_status FROM reviews WHERE clause_id = ?",
                (clause["id"],),
            ).fetchall()

            highest = None
            open_count = 0
            for rv in reviews:
                level = RiskLevel(rv["risk_level"])
                if rv["process_status"] == ProcessStatus.open.value:
                    breakdown[level]["unprocessed_count"] += 1
                    open_count += 1
                elif rv["process_status"] == ProcessStatus.resolved.value:
                    breakdown[level]["resolved_count"] += 1
                if highest is None or _RISK_ORDER[level] > _RISK_ORDER[highest]:
                    highest = level

            tags = ClauseTagRepository.list_tags_for_clause(conn, clause["id"])
            if tags:
                tagged_clause_count += 1

            if highest is not None:
                top_risk_clauses.append({
                    "clause_id": clause["id"],
                    "clause_no": clause["clause_no"],
                    "highest_risk_level": highest.value,
                    "open_count": open_count,
                })
                # A high-risk clause with no risk-tag classification is a gap.
                if highest in _HIGH_RISK and not tags:
                    untagged_high_risk.append({
                        "clause_id": clause["id"],
                        "clause_no": clause["clause_no"],
                        "highest_risk_level": highest.value,
                    })

        # Highest risk first; stable by clause id for ties.
        top_risk_clauses.sort(
            key=lambda c: (-_RISK_ORDER[RiskLevel(c["highest_risk_level"])],
                           c["clause_id"])
        )

        risk_breakdown = [
            {
                "risk_level": level.value,
                "unprocessed_count": breakdown[level]["unprocessed_count"],
                "resolved_count": breakdown[level]["resolved_count"],
            }
            for level in RiskLevel
        ]

        return {
            "document_id": doc["id"],
            "document_title": doc["title"],
            "include_deprecated": include_deprecated,
            "considered_clauses": len(clauses),
            "tagged_clause_count": tagged_clause_count,
            "risk_breakdown": risk_breakdown,
            "top_risk_clauses": top_risk_clauses,
            "untagged_high_risk_clauses": untagged_high_risk,
        }


# ---------------------------------------------------------------------------
# Document version copy
# ---------------------------------------------------------------------------
def copy_document(source_document_id: int, payload) -> dict:
    """Create a new document version from an existing one.

    Copy semantics (reusing the tag-binding meaning from earlier rounds — tags
    are clause-level risk classifications, never comment status):
      * only non-deprecated clauses are carried forward;
      * each copied clause inherits its source clause's risk-tag bindings;
      * reviews are never copied — resolved comments in particular are dropped;
      * the response reports provenance and skip counts so risk inheritance and
        handling progress can be reconstructed later.
    """
    with transaction() as conn:
        source = DocumentRepository.get(conn, source_document_id)

        target = DocumentRepository.create(
            conn,
            title=payload.title or source["title"],
            source_department=source["source_department"],
            version_no=payload.version_no,
            document_status=source["document_status"],
        )

        copied_tag_count = 0
        skipped_deprecated_count = 0
        skipped_resolved_comment_count = 0
        pending_maps = []  # (source_clause_id, target_clause_id, clause_no, tags)

        for clause in ClauseRepository.list_for_document(conn, source_document_id):
            if clause["deprecated"]:
                skipped_deprecated_count += 1
                continue  # deprecated clauses are not carried forward

            # Reviews are never copied; count resolved ones we deliberately drop.
            skipped_resolved_comment_count += _count_resolved_reviews(
                conn, clause["id"]
            )

            new_clause = ClauseRepository.create(
                conn,
                document_id=target["id"],
                clause_no=clause["clause_no"],
                clause_text=clause["clause_text"],
                clause_type=clause["clause_type"],
                importance=clause["importance"],
                deprecated=False,
            )
            inherited = ClauseTagRepository.list_tags_for_clause(conn, clause["id"])
            for tag in inherited:
                ClauseTagRepository.bind(conn, new_clause["id"], tag["tag_id"])
                copied_tag_count += 1
            pending_maps.append(
                (clause["id"], new_clause["id"], clause["clause_no"], inherited)
            )

        copy = DocumentCopyRepository.create(
            conn,
            source_document_id,
            target["id"],
            copied_tag_count=copied_tag_count,
            skipped_deprecated_count=skipped_deprecated_count,
            skipped_resolved_comment_count=skipped_resolved_comment_count,
        )

        clause_mappings = []
        for src_id, tgt_id, clause_no, inherited in pending_maps:
            CopyClauseMapRepository.create(
                conn,
                copy_id=copy["id"],
                source_clause_id=src_id,
                target_clause_id=tgt_id,
            )
            clause_mappings.append({
                "source_clause_id": src_id,
                "target_clause_id": tgt_id,
                "clause_no": clause_no,
                "inherited_tags": inherited,
            })

        return {
            "source_document_id": source_document_id,
            "target_document_id": target["id"],
            "clause_mappings": clause_mappings,
            "copied_tag_count": copied_tag_count,
            "skipped_deprecated_count": skipped_deprecated_count,
            "skipped_resolved_comment_count": skipped_resolved_comment_count,
            "target_document": target,
        }


def _count_resolved_reviews(conn, clause_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM reviews WHERE clause_id = ? AND process_status = ?",
        (clause_id, ProcessStatus.resolved.value),
    ).fetchone()
    return row["c"]


def get_copy_detail(target_document_id: int) -> dict:
    """Per-clause detail for a copied document: origin, inherited tags, and a
    summary of what was not copied for each new clause."""
    with transaction() as conn:
        DocumentRepository.get(conn, target_document_id)  # 404 if missing
        copy = DocumentCopyRepository.get_by_target(conn, target_document_id)

        clauses = []
        for m in CopyClauseMapRepository.list_for_copy(conn, copy["id"]):
            source_clause = ClauseRepository.get(conn, m["source_clause_id"])
            target_clause = ClauseRepository.get(conn, m["target_clause_id"])
            inherited = ClauseTagRepository.list_tags_for_clause(
                conn, m["target_clause_id"]
            )
            # Reasons for what did not carry over onto this new clause.
            not_copied = []
            resolved = _count_resolved_reviews(conn, m["source_clause_id"])
            total_reviews = conn.execute(
                "SELECT COUNT(*) AS c FROM reviews WHERE clause_id = ?",
                (m["source_clause_id"],),
            ).fetchone()["c"]
            if total_reviews:
                not_copied.append(
                    f"{total_reviews} review comment(s) not copied "
                    f"({resolved} resolved)."
                )
            clauses.append({
                "target_clause_id": target_clause["id"],
                "target_clause_no": target_clause["clause_no"],
                "source_clause_id": source_clause["id"],
                "source_clause_no": source_clause["clause_no"],
                "inherited_tags": inherited,
                "not_copied_summary": not_copied,
            })

        return {
            "copy_id": copy["id"],
            "source_document_id": copy["source_document_id"],
            "target_document_id": copy["target_document_id"],
            "copied_tag_count": copy["copied_tag_count"],
            "skipped_deprecated_count": copy["skipped_deprecated_count"],
            "skipped_resolved_comment_count": copy["skipped_resolved_comment_count"],
            "created_at": copy["created_at"],
            "clauses": clauses,
        }


def get_copy_mappings(source_document_id: int) -> list[dict]:
    with transaction() as conn:
        DocumentRepository.get(conn, source_document_id)
        return DocumentCopyRepository.list_for_source(conn, source_document_id)


# ---------------------------------------------------------------------------
# Consistency self-check
# ---------------------------------------------------------------------------
# Ordered list of (check name, repository function). Names are stable so the
# acceptance team can rely on them.
_CONSISTENCY_CHECKS = [
    ("reviews_added_after_deprecation",
     ConsistencyRepository.reviews_on_clause_after_deprecation),
    ("tags_bound_after_deprecation",
     ConsistencyRepository.tags_bound_after_deprecation),
    ("resolved_reviews_without_process_record",
     ConsistencyRepository.resolved_reviews_without_record),
    ("duplicate_tag_bindings",
     ConsistencyRepository.duplicate_tag_bindings),
    ("missing_copy_mappings",
     ConsistencyRepository.missing_copy_mappings),
    ("dashboard_detail_mismatch",
     ConsistencyRepository.dashboard_detail_mismatch),
    ("duplicate_clause_no",
     ConsistencyRepository.duplicate_clause_no),
    ("non_open_reviews_in_unprocessed",
     ConsistencyRepository.non_open_in_unprocessed),
]


def run_consistency_check() -> dict:
    """Audit the whole ledger and return one uniform report.

    Every check runs regardless of others' outcomes, so the report always lists
    all checks with their pass state, problem count and problem details.
    """
    with transaction() as conn:
        checks = []
        total_problems = 0
        for name, fn in _CONSISTENCY_CHECKS:
            details = fn(conn)
            problem_count = len(details)
            total_problems += problem_count
            checks.append({
                "name": name,
                "passed": problem_count == 0,
                "problem_count": problem_count,
                "details": details,
            })
        return {
            "healthy": total_problems == 0,
            "total_problems": total_problems,
            "generated_at": now_iso(),
            "checks": checks,
        }

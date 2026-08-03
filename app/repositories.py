"""Repository layer: all SQL lives here.

Every function takes a live ``sqlite3.Connection`` (supplied by
:func:`app.database.transaction`) so the service layer controls transaction
boundaries. Repositories return plain ``dict`` objects with snake_case keys so
the service/schema layers never touch ``sqlite3.Row``.

Repositories perform *storage-level* validation only (e.g. uniqueness). Higher
business rules (deprecation guards, state transitions) live in the service layer.
"""

from __future__ import annotations

import sqlite3

from .enums import ImportMode, ProcessStatus
from .exceptions import ConflictError, NotFoundError
from .utils import now_iso


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentRepository:
    @staticmethod
    def create(conn, *, title, source_department, version_no, document_status) -> dict:
        created_at = now_iso()
        cur = conn.execute(
            """INSERT INTO documents
               (title, source_department, version_no, document_status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (title, source_department, version_no, document_status, created_at),
        )
        return DocumentRepository.get(conn, cur.lastrowid)

    @staticmethod
    def get(conn, document_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Document {document_id} was not found.",
                details={"document_id": document_id},
            )
        return dict(row)

    @staticmethod
    def update_status(conn, document_id: int, document_status: str) -> dict:
        DocumentRepository.get(conn, document_id)  # existence check
        conn.execute(
            "UPDATE documents SET document_status = ? WHERE id = ?",
            (document_status, document_id),
        )
        return DocumentRepository.get(conn, document_id)


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
class ClauseRepository:
    @staticmethod
    def get(conn, clause_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM clauses WHERE id = ?", (clause_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Clause {clause_id} was not found.",
                details={"clause_id": clause_id},
            )
        return _normalise_clause(dict(row))

    @staticmethod
    def get_by_no(conn, document_id: int, clause_no: str) -> dict | None:
        row = conn.execute(
            "SELECT * FROM clauses WHERE document_id = ? AND clause_no = ?",
            (document_id, clause_no),
        ).fetchone()
        return _normalise_clause(dict(row)) if row else None

    @staticmethod
    def list_for_document(conn, document_id: int) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM clauses WHERE document_id = ? ORDER BY id",
            (document_id,),
        ).fetchall()
        return [_normalise_clause(dict(r)) for r in rows]

    @staticmethod
    def create(conn, *, document_id, clause_no, clause_text, clause_type,
               importance, deprecated=False) -> dict:
        if ClauseRepository.get_by_no(conn, document_id, clause_no) is not None:
            raise ConflictError(
                f"clause_no '{clause_no}' already exists in document {document_id}.",
                details={"document_id": document_id, "clause_no": clause_no},
            )
        cur = conn.execute(
            """INSERT INTO clauses
               (document_id, clause_no, clause_text, clause_type, importance, deprecated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (document_id, clause_no, clause_text, clause_type, importance,
             1 if deprecated else 0),
        )
        return ClauseRepository.get(conn, cur.lastrowid)

    @staticmethod
    def update_content(conn, clause_id: int, *, clause_text, clause_type,
                       importance) -> dict:
        conn.execute(
            """UPDATE clauses
               SET clause_text = ?, clause_type = ?, importance = ?
               WHERE id = ?""",
            (clause_text, clause_type, importance, clause_id),
        )
        return ClauseRepository.get(conn, clause_id)

    @staticmethod
    def set_deprecated(conn, clause_id: int, deprecated: bool) -> dict:
        ClauseRepository.get(conn, clause_id)
        # Record when the clause was deprecated so consistency checks can spot
        # reviews/tags added after the fact.
        deprecated_at = now_iso() if deprecated else None
        conn.execute(
            "UPDATE clauses SET deprecated = ?, deprecated_at = ? WHERE id = ?",
            (1 if deprecated else 0, deprecated_at, clause_id),
        )
        return ClauseRepository.get(conn, clause_id)


def _normalise_clause(row: dict) -> dict:
    row["deprecated"] = bool(row["deprecated"])
    return row


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
class ReviewRepository:
    @staticmethod
    def get(conn, review_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Review {review_id} was not found.",
                details={"review_id": review_id},
            )
        return dict(row)

    @staticmethod
    def create(conn, *, clause_id, reviewer_name, comment_text, risk_level,
               process_status=ProcessStatus.open.value) -> dict:
        created_at = now_iso()
        cur = conn.execute(
            """INSERT INTO reviews
               (clause_id, reviewer_name, comment_text, risk_level, process_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (clause_id, reviewer_name, comment_text, risk_level,
             process_status, created_at),
        )
        return ReviewRepository.get(conn, cur.lastrowid)

    @staticmethod
    def update_status(conn, review_id: int, process_status: str) -> dict:
        conn.execute(
            "UPDATE reviews SET process_status = ? WHERE id = ?",
            (process_status, review_id),
        )
        return ReviewRepository.get(conn, review_id)

    @staticmethod
    def latest_for_clause(conn, clause_id: int) -> dict | None:
        row = conn.execute(
            """SELECT * FROM reviews WHERE clause_id = ?
               ORDER BY id DESC LIMIT 1""",
            (clause_id,),
        ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def list_unprocessed_by_risk(conn, risk_level: str) -> list[dict]:
        """Reviews at a given risk level that are still 'open'."""
        rows = conn.execute(
            """SELECT * FROM reviews
               WHERE risk_level = ? AND process_status = ?
               ORDER BY id""",
            (risk_level, ProcessStatus.open.value),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Risk tags & bindings
# ---------------------------------------------------------------------------
class RiskTagRepository:
    @staticmethod
    def get(conn, tag_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM risk_tags WHERE id = ?", (tag_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Risk tag {tag_id} was not found.",
                details={"tag_id": tag_id},
            )
        return dict(row)

    @staticmethod
    def create(conn, *, name, description=None) -> dict:
        existing = conn.execute(
            "SELECT id FROM risk_tags WHERE name = ?", (name,)
        ).fetchone()
        if existing is not None:
            raise ConflictError(
                f"A risk tag named '{name}' already exists.",
                details={"name": name},
            )
        created_at = now_iso()
        cur = conn.execute(
            "INSERT INTO risk_tags (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, created_at),
        )
        return RiskTagRepository.get(conn, cur.lastrowid)


class ClauseTagRepository:
    @staticmethod
    def bind(conn, clause_id: int, tag_id: int) -> dict:
        existing = conn.execute(
            "SELECT * FROM clause_tags WHERE clause_id = ? AND tag_id = ?",
            (clause_id, tag_id),
        ).fetchone()
        if existing is not None:
            raise ConflictError(
                f"Tag {tag_id} is already bound to clause {clause_id}.",
                details={"clause_id": clause_id, "tag_id": tag_id},
            )
        created_at = now_iso()
        cur = conn.execute(
            "INSERT INTO clause_tags (clause_id, tag_id, created_at) VALUES (?, ?, ?)",
            (clause_id, tag_id, created_at),
        )
        row = conn.execute(
            "SELECT * FROM clause_tags WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def list_for_clause(conn, clause_id: int) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM clause_tags WHERE clause_id = ? ORDER BY id",
            (clause_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def list_tags_for_clause(conn, clause_id: int) -> list[dict]:
        """Return the risk tags (id + name) bound to a clause.

        These are clause-level risk classifications — never comment status.
        """
        rows = conn.execute(
            """SELECT rt.id AS tag_id, rt.name AS tag_name
               FROM clause_tags ct
               JOIN risk_tags rt ON rt.id = ct.tag_id
               WHERE ct.clause_id = ?
               ORDER BY rt.id""",
            (clause_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Process records
# ---------------------------------------------------------------------------
class ProcessRecordRepository:
    @staticmethod
    def create(conn, *, review_id, from_status, to_status, operator, note=None) -> dict:
        created_at = now_iso()
        cur = conn.execute(
            """INSERT INTO process_records
               (review_id, from_status, to_status, operator, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (review_id, from_status, to_status, operator, note, created_at),
        )
        row = conn.execute(
            "SELECT * FROM process_records WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def list_for_review(conn, review_id: int) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM process_records WHERE review_id = ? ORDER BY id",
            (review_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Document copies
# ---------------------------------------------------------------------------
class DocumentCopyRepository:
    @staticmethod
    def create(conn, source_document_id: int, target_document_id: int, *,
               copied_tag_count=0, skipped_deprecated_count=0,
               skipped_resolved_comment_count=0) -> dict:
        created_at = now_iso()
        cur = conn.execute(
            """INSERT INTO document_copies
               (source_document_id, target_document_id, copied_tag_count,
                skipped_deprecated_count, skipped_resolved_comment_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source_document_id, target_document_id, copied_tag_count,
             skipped_deprecated_count, skipped_resolved_comment_count, created_at),
        )
        row = conn.execute(
            "SELECT * FROM document_copies WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def get(conn, copy_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM document_copies WHERE id = ?", (copy_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Document copy {copy_id} was not found.",
                details={"copy_id": copy_id},
            )
        return dict(row)

    @staticmethod
    def get_by_target(conn, target_document_id: int) -> dict:
        row = conn.execute(
            "SELECT * FROM document_copies WHERE target_document_id = ?",
            (target_document_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                f"No copy record produced document {target_document_id}.",
                details={"target_document_id": target_document_id},
            )
        return dict(row)

    @staticmethod
    def list_for_source(conn, source_document_id: int) -> list[dict]:
        rows = conn.execute(
            """SELECT * FROM document_copies
               WHERE source_document_id = ? ORDER BY id""",
            (source_document_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Copy clause map (per-clause provenance for a copy)
# ---------------------------------------------------------------------------
class CopyClauseMapRepository:
    @staticmethod
    def create(conn, *, copy_id, source_clause_id, target_clause_id) -> dict:
        created_at = now_iso()
        cur = conn.execute(
            """INSERT INTO copy_clause_map
               (copy_id, source_clause_id, target_clause_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (copy_id, source_clause_id, target_clause_id, created_at),
        )
        row = conn.execute(
            "SELECT * FROM copy_clause_map WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    @staticmethod
    def list_for_copy(conn, copy_id: int) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM copy_clause_map WHERE copy_id = ? ORDER BY id",
            (copy_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Consistency self-check
# ---------------------------------------------------------------------------
class ConsistencyRepository:
    """Read-only ledger self-audit.

    Each method returns a list of *problem* detail dicts (empty list == healthy).
    The checks read raw rows so they can catch inconsistencies even if data was
    written outside the normal service guards.
    """

    @staticmethod
    def reviews_on_clause_after_deprecation(conn) -> list[dict]:
        """Reviews created after their clause was deprecated."""
        rows = conn.execute(
            """SELECT r.id AS review_id, r.clause_id, c.deprecated_at,
                      r.created_at AS review_created_at
               FROM reviews r
               JOIN clauses c ON c.id = r.clause_id
               WHERE c.deprecated = 1
                 AND c.deprecated_at IS NOT NULL
                 AND r.created_at > c.deprecated_at
               ORDER BY r.id""",
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def tags_bound_after_deprecation(conn) -> list[dict]:
        """Tag bindings created after their clause was deprecated."""
        rows = conn.execute(
            """SELECT ct.id AS clause_tag_id, ct.clause_id, ct.tag_id,
                      c.deprecated_at, ct.created_at AS bound_at
               FROM clause_tags ct
               JOIN clauses c ON c.id = ct.clause_id
               WHERE c.deprecated = 1
                 AND c.deprecated_at IS NOT NULL
                 AND ct.created_at > c.deprecated_at
               ORDER BY ct.id""",
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def resolved_reviews_without_record(conn) -> list[dict]:
        """resolved reviews with no matching process record to resolved."""
        rows = conn.execute(
            """SELECT r.id AS review_id, r.clause_id
               FROM reviews r
               WHERE r.process_status = 'resolved'
                 AND NOT EXISTS (
                     SELECT 1 FROM process_records pr
                     WHERE pr.review_id = r.id AND pr.to_status = 'resolved'
                 )
               ORDER BY r.id""",
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def duplicate_tag_bindings(conn) -> list[dict]:
        """Same tag bound to the same clause more than once."""
        rows = conn.execute(
            """SELECT clause_id, tag_id, COUNT(*) AS binding_count
               FROM clause_tags
               GROUP BY clause_id, tag_id
               HAVING COUNT(*) > 1
               ORDER BY clause_id, tag_id""",
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def missing_copy_mappings(conn) -> list[dict]:
        """copy_clause_map rows whose parent copy record is missing, or
        document_copies rows that produced clauses but have no clause map."""
        problems = []
        orphans = conn.execute(
            """SELECT ccm.id AS copy_clause_map_id, ccm.copy_id
               FROM copy_clause_map ccm
               WHERE NOT EXISTS (
                   SELECT 1 FROM document_copies dc WHERE dc.id = ccm.copy_id
               )
               ORDER BY ccm.id""",
        ).fetchall()
        for row in orphans:
            problems.append({**dict(row), "reason": "orphan_clause_map"})

        # A copy whose target document has clauses but no per-clause mapping.
        gaps = conn.execute(
            """SELECT dc.id AS copy_id, dc.target_document_id
               FROM document_copies dc
               WHERE (SELECT COUNT(*) FROM clauses c
                      WHERE c.document_id = dc.target_document_id) > 0
                 AND NOT EXISTS (
                     SELECT 1 FROM copy_clause_map ccm WHERE ccm.copy_id = dc.id
                 )
               ORDER BY dc.id""",
        ).fetchall()
        for row in gaps:
            problems.append({**dict(row), "reason": "missing_clause_map"})
        return problems

    @staticmethod
    def dashboard_detail_mismatch(conn) -> list[dict]:
        """Dashboard aggregate vs. raw detail count must agree.

        The dashboard counts reviews by joining through a document's clauses.
        The detail count is the raw number of review rows. They can only diverge
        when a review points at a clause that no longer exists (a dangling
        review), which every per-document tally would silently drop.
        """
        problems = []
        aggregate = conn.execute(
            """SELECT COUNT(*) AS c FROM reviews r
               JOIN clauses c ON c.id = r.clause_id""",
        ).fetchone()["c"]
        detail = conn.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"]
        if aggregate != detail:
            dangling = conn.execute(
                """SELECT id AS review_id, clause_id FROM reviews
                   WHERE clause_id NOT IN (SELECT id FROM clauses)
                   ORDER BY id""",
            ).fetchall()
            for row in dangling:
                problems.append({**dict(row), "reason": "dangling_review"})
            if not dangling:  # divergence without an obvious dangling row
                problems.append({
                    "aggregate_count": aggregate,
                    "detail_count": detail,
                    "reason": "count_mismatch",
                })
        return problems

    @staticmethod
    def duplicate_clause_no(conn) -> list[dict]:
        """Same clause_no appearing twice within one document."""
        rows = conn.execute(
            """SELECT document_id, clause_no, COUNT(*) AS clause_count
               FROM clauses
               GROUP BY document_id, clause_no
               HAVING COUNT(*) > 1
               ORDER BY document_id, clause_no""",
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def non_open_in_unprocessed(conn) -> list[dict]:
        """Reviews that would be misclassified by the unprocessed listing.

        The unprocessed listing returns reviews whose process_status is 'open'.
        The invariant is that resolved/rejected reviews never appear there. We
        validate it by scanning for any review whose status is NOT a recognised
        value (open/accepted/rejected/resolved): such a row cannot be correctly
        bucketed as processed vs. unprocessed and would corrupt the listing.
        """
        rows = conn.execute(
            """SELECT id AS review_id, clause_id, process_status, risk_level
               FROM reviews
               WHERE process_status NOT IN
                     ('open', 'accepted', 'rejected', 'resolved')
               ORDER BY id""",
        ).fetchall()
        return [dict(r) for r in rows]

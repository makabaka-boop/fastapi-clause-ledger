"""SQLite connection helpers and schema bootstrap.

A thin wrapper over the stdlib ``sqlite3`` module. We deliberately avoid an ORM
so the repository layer stays explicit and the relational model is visible in
one place. Foreign keys are enabled on every connection and rows come back as
``sqlite3.Row`` so repositories can address columns by name.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# All timestamps are stored as ISO 8601 strings (UTC) so the API can echo them
# back verbatim without any conversion.

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    source_department TEXT   NOT NULL,
    version_no       TEXT    NOT NULL,
    document_status  TEXT    NOT NULL,
    created_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS clauses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    clause_no   TEXT    NOT NULL,
    clause_text TEXT    NOT NULL,
    clause_type TEXT    NOT NULL,
    importance  TEXT    NOT NULL,
    deprecated  INTEGER NOT NULL DEFAULT 0,
    deprecated_at TEXT,
    UNIQUE (document_id, clause_no)
);

CREATE TABLE IF NOT EXISTS reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_id      INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    reviewer_name  TEXT    NOT NULL,
    comment_text   TEXT    NOT NULL,
    risk_level     TEXT    NOT NULL,
    process_status TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS clause_tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_id  INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES risk_tags(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    UNIQUE (clause_id, tag_id)
);

CREATE TABLE IF NOT EXISTS process_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id   INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    from_status TEXT    NOT NULL,
    to_status   TEXT    NOT NULL,
    operator    TEXT    NOT NULL,
    note        TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS document_copies (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    copied_tag_count             INTEGER NOT NULL DEFAULT 0,
    skipped_deprecated_count     INTEGER NOT NULL DEFAULT 0,
    skipped_resolved_comment_count INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    UNIQUE (source_document_id, target_document_id)
);

-- Per-clause provenance for a copy: which source clause produced which target
-- clause. Enables the copy-detail endpoint to show risk inheritance precisely.
CREATE TABLE IF NOT EXISTS copy_clause_map (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    copy_id          INTEGER NOT NULL REFERENCES document_copies(id) ON DELETE CASCADE,
    source_clause_id INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    target_clause_id INTEGER NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    created_at       TEXT    NOT NULL
);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open a new connection with sane defaults for this service."""
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create all tables if they do not yet exist."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection wrapped in a transaction.

    Commits on success, rolls back on any exception, and always closes the
    connection. Repositories receive the live connection so several operations
    can share one atomic unit of work.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

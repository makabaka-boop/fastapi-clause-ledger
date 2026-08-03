import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.clause import Clause
from app.models.comment import Comment
from app.services.consistency_service import ConsistencyService
from tests.helpers import (
    add_comment,
    create_clauses,
    create_document,
    create_tag,
)


def _checks_by_name(report):
    return {c["check_name"]: c for c in report["checks"]}


def test_consistency_check_passes_on_clean_data(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings",
                json={"clause_id": 1, "tag_id": tag["id"]})
    add_comment(client, 1, risk="high")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})
    client.post(f"/api/v1/documents/{doc['id']}/copy",
                json={"new_version_no": "v2"})

    resp = client.get("/api/v1/consistency/check")
    assert resp.status_code == 200
    report = resp.json()
    assert report["all_passed"] is True
    assert report["failed_checks"] == 0
    assert report["total_checks"] == 7
    for check in report["checks"]:
        assert check["passed"] is True
        assert check["issue_count"] == 0
        assert "check_name" in check
        assert "details" in check


def test_consistency_detects_comment_on_deprecated_clause(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, risk="high")
    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    resp = client.get("/api/v1/consistency/check")
    report = resp.json()
    assert report["all_passed"] is False
    check = _checks_by_name(report)["comments_on_deprecated_clauses"]
    assert check["passed"] is False
    assert check["issue_count"] == 1
    assert check["details"][0]["comment_id"] == 1
    assert check["details"][0]["clause_id"] == 1


def test_consistency_detects_resolved_comment_missing_record(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, risk="high")

    from app.database import SessionLocal
    db = SessionLocal()
    try:
        comment = db.query(Comment).filter(Comment.id == 1).one()
        comment.process_status = "resolved"
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/consistency/check")
    report = resp.json()
    check = _checks_by_name(report)["resolved_comments_missing_records"]
    assert check["passed"] is False
    assert check["issue_count"] == 1
    assert check["details"][0]["comment_id"] == 1


@pytest.fixture()
def unconstrained_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE documents ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "title VARCHAR(500), source_department VARCHAR(200), "
            "version_no VARCHAR(100), document_status VARCHAR(50), "
            "created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE clauses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "document_id INTEGER, clause_no VARCHAR(100), "
            "clause_text TEXT, clause_type VARCHAR(100), "
            "importance INTEGER, deprecated BOOLEAN, created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE comments ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "clause_id INTEGER, reviewer_name VARCHAR(200), "
            "comment_text TEXT, risk_level VARCHAR(20), "
            "process_status VARCHAR(20), created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE tags ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(200))"
        ))
        conn.execute(text(
            "CREATE TABLE tag_bindings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "clause_id INTEGER, tag_id INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE process_records ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "comment_id INTEGER, from_status VARCHAR(20), "
            "to_status VARCHAR(20), note TEXT, "
            "operator VARCHAR(200), created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE copy_mappings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "source_document_id INTEGER, target_document_id INTEGER, "
            "copied_by VARCHAR(200), created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE clause_copy_mappings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "copy_mapping_id INTEGER, source_clause_id INTEGER, "
            "target_clause_id INTEGER)"
        ))
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_consistency_detects_duplicate_clause_no(unconstrained_session):
    db = unconstrained_session
    now = "2026-01-01 00:00:00"
    db.execute(text(
        "INSERT INTO documents (id, title, source_department, version_no, "
        "document_status, created_at) VALUES (1, 'd', 'Legal', 'v1', 'draft', :t)"
    ), {"t": now})
    db.execute(text(
        "INSERT INTO clauses (id, document_id, clause_no, clause_text, "
        "clause_type, importance, deprecated, created_at) "
        "VALUES (1, 1, '1.1', 'first', 't', 1, 0, :t)"
    ), {"t": now})
    db.execute(text(
        "INSERT INTO clauses (id, document_id, clause_no, clause_text, "
        "clause_type, importance, deprecated, created_at) "
        "VALUES (2, 1, '1.1', 'duplicate', 't', 1, 0, :t)"
    ), {"t": now})
    db.commit()

    svc = ConsistencyService(db)
    check = svc._check_duplicate_clause_no()
    assert check["passed"] is False
    assert check["issue_count"] == 1
    assert check["details"][0]["clause_no"] == "1.1"
    assert check["details"][0]["document_id"] == 1


def test_consistency_detects_duplicate_tag_bindings(unconstrained_session):
    db = unconstrained_session
    db.execute(text(
        "INSERT INTO tags (id, name) VALUES (1, 'privacy')"
    ))
    db.execute(text(
        "INSERT INTO tag_bindings (id, clause_id, tag_id) VALUES (1, 10, 1)"
    ))
    db.execute(text(
        "INSERT INTO tag_bindings (id, clause_id, tag_id) VALUES (2, 10, 1)"
    ))
    db.commit()

    svc = ConsistencyService(db)
    check = svc._check_duplicate_tag_bindings()
    assert check["passed"] is False
    assert check["issue_count"] == 1
    assert check["details"][0]["clause_id"] == 10
    assert check["details"][0]["tag_id"] == 1


def test_consistency_detects_rejected_not_in_unresolved(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, risk="high")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "rejected", "note": "no"})

    resp = client.get("/api/v1/consistency/check")
    report = resp.json()
    check = _checks_by_name(report)["terminal_comments_in_unresolved"]
    assert check["passed"] is True
    assert check["issue_count"] == 0

    unresolved = client.get(
        "/api/v1/comments/unresolved",
        params={"risk_level": "high"},
    ).json()
    assert unresolved == []


def test_consistency_detects_missing_copy_mapping(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    copy_resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2"},
    )
    target_id = copy_resp.json()["target_document_id"]

    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.add(Clause(
            document_id=target_id,
            clause_no="9.9",
            clause_text="orphan",
            clause_type="t",
            importance=1,
            deprecated=False,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/consistency/check")
    report = resp.json()
    check = _checks_by_name(report)["missing_copy_mappings"]
    assert check["passed"] is False
    assert any(
        d["type"] == "unmapped_target_clause"
        for d in check["details"]
    )


def test_consistency_dashboard_stats_consistency(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 3},
        {"clause_no": "1.2", "clause_text": "y", "clause_type": "t", "importance": 2},
    ])
    add_comment(client, 1, risk="critical")
    add_comment(client, 2, risk="low")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    resp = client.get("/api/v1/consistency/check")
    report = resp.json()
    check = _checks_by_name(report)["dashboard_stats_consistency"]
    assert check["passed"] is True

    dash = client.get(
        f"/api/v1/dashboard/documents/{doc['id']}/risk"
    ).json()
    assert dash["unresolved_by_risk"]["critical"] == 0
    assert dash["unresolved_by_risk"]["low"] == 1
    assert dash["resolved_count"] == 1


def test_all_new_endpoints_use_api_v1_prefix(client):
    resp = client.get("/api/v1/consistency/check")
    assert resp.status_code == 200
    for route in client.app.routes:
        if hasattr(route, "path") and route.path.startswith("/api"):
            assert route.path.startswith("/api/v1"), route.path

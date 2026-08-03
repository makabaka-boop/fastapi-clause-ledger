from fastapi.testclient import TestClient


def _create_doc(client: TestClient, title: str = "Policy", version: str = "1.0") -> dict:
    return client.post(
        "/api/v1/documents",
        json={"title": title, "source_department": "Legal", "version_no": version},
    ).json()


def _add_clause(client: TestClient, doc_id: int, no: str = "1.1", text: str = "Text") -> dict:
    return client.post(
        f"/api/v1/documents/{doc_id}/clauses/batch",
        json={"clauses": [{"clause_no": no, "clause_text": text}]},
    ).json()[0]


# ---------- 自检通过 ----------

def test_consistency_check_passes_for_clean_data(client: TestClient) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    tag = client.post("/api/v1/risk-tags", json={"name": "GDPR"}).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )

    resp = client.get("/api/v1/consistency/check")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] is True
    assert body["total_checks"] == 7
    assert body["failed_checks"] == 0
    assert body["total_issues"] == 0
    assert len(body["checks"]) == 7
    for check in body["checks"]:
        assert {"name", "passed", "issue_count", "issues"} <= set(check.keys())
    assert "checked_at" in body


# ---------- 自检异常 ----------

def test_consistency_detects_resolved_comment_without_record(
    client: TestClient, db_session
) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "high"},
    ).json()

    from app import models

    db_session.query(models.Comment).filter_by(id=comment["id"]).update(
        {models.Comment.process_status: "resolved"}
    )
    db_session.commit()

    resp = client.get("/api/v1/consistency/check")
    body = resp.json()
    assert body["passed"] is False

    check = next(
        c for c in body["checks"]
        if c["name"] == "resolved_comments_missing_processing_records"
    )
    assert check["passed"] is False
    assert check["issue_count"] == 1
    assert check["issues"][0]["entity_id"] == comment["id"]


def test_consistency_detects_deprecated_clause_with_comment(
    client: TestClient,
) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "low"},
    )
    client.post(f"/api/v1/clauses/{clause['id']}/deprecate")

    body = client.get("/api/v1/consistency/check").json()
    check = next(
        c for c in body["checks"] if c["name"] == "comments_on_deprecated_clauses"
    )
    assert check["passed"] is False
    assert check["issue_count"] == 1


def test_consistency_detects_broken_copy_mapping(client: TestClient, db_session) -> None:
    from app import models

    doc = _create_doc(client)
    target = _create_doc(client, title="Policy", version="2.0")
    db_session.add(
        models.DocumentCopy(
            source_document_id=doc["id"],
            target_document_id=999999,
            copy_type="version_copy",
        )
    )
    db_session.commit()

    body = client.get("/api/v1/consistency/check").json()
    check = next(c for c in body["checks"] if c["name"] == "document_copy_mappings")
    assert check["passed"] is False
    assert any(i["details"]["target_exists"] is False for i in check["issues"])


def test_consistency_duplicate_clause_no_check_present(client: TestClient) -> None:
    doc = _create_doc(client)
    _add_clause(client, doc["id"], no="1.1")

    body = client.get("/api/v1/consistency/check").json()
    check = next(
        c for c in body["checks"] if c["name"] == "duplicate_clause_no_within_document"
    )
    assert check["passed"] is True
    assert check["issue_count"] == 0


# ---------- 未处理口径：rejected/resolved 不出现 ----------

def test_rejected_comment_not_in_unresolved_list(client: TestClient) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "rejected", "operator": "lead"},
    )

    resp = client.get(
        "/api/v1/comments/unresolved", params={"risk_level": "high"}
    )
    assert resp.status_code == 200
    assert all(c["id"] != comment["id"] for c in resp.json())


def test_resolved_comment_not_in_unresolved_list(client: TestClient) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "resolved", "operator": "lead"},
    )

    resp = client.get(
        "/api/v1/comments/unresolved", params={"risk_level": "high"}
    )
    assert all(c["id"] != comment["id"] for c in resp.json())


def test_dashboard_excludes_rejected_from_unresolved(client: TestClient) -> None:
    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "risk", "risk_level": "critical"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "rejected", "operator": "lead"},
    )

    board = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk").json()
    assert board["unresolved_by_risk"]["critical"] == 0
    assert board["resolved_by_risk"]["critical"] == 1
    assert board["total_unresolved"] == 0
    assert board["total_resolved"] == 1


# ---------- 所有新接口保持 /api/v1 前缀 ----------

def test_all_new_endpoints_use_api_v1_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/consistency/check").status_code == 200

    assert client.get("/consistency/check").status_code == 404

    doc = _create_doc(client)
    clause = _add_clause(client, doc["id"])
    comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "x", "risk_level": "low"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "resolved", "operator": "lead"},
    )
    copy = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "2.0"},
    ).json()
    detail = client.get(
        f"/api/v1/document-copies/{copy['target_document_id']}/detail"
    )
    assert detail.status_code == 200

    risk = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    assert risk.status_code == 200


# ---------- README 关键端到端流程可执行 ----------

def test_readme_end_to_end_flow(client: TestClient) -> None:
    doc = client.post(
        "/api/v1/documents",
        json={
            "title": "Vendor Agreement",
            "source_department": "Procurement",
            "version_no": "1.0",
        },
    )
    assert doc.status_code == 201
    doc_id = doc.json()["id"]

    imported = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {"clause_no": "1", "clause_text": "Confidentiality", "importance": "high"},
                {"clause_no": "2", "clause_text": "Liability", "importance": "medium"},
            ],
        },
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 2

    clause_1 = next(
        c for c in imported.json()["clauses"] if c["clause_no"] == "1"
    )

    comment = client.post(
        f"/api/v1/clauses/{clause_1['id']}/comments",
        json={
            "reviewer_name": "Alice",
            "comment_text": "Clarify data handling",
            "risk_level": "high",
        },
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    tag = client.post(
        "/api/v1/risk-tags",
        json={"name": "DataPrivacy", "description": "Personal data"},
    )
    assert tag.status_code == 201
    tag_id = tag.json()["id"]

    bind = client.post(
        f"/api/v1/risk-tags/clauses/{clause_1['id']}/bindings",
        json={"tag_id": tag_id},
    )
    assert bind.status_code == 201

    accepted = client.patch(
        f"/api/v1/comments/{comment_id}/status",
        json={"process_status": "accepted", "operator": "Bob", "note": "ack"},
    )
    assert accepted.status_code == 200
    resolved = client.patch(
        f"/api/v1/comments/{comment_id}/status",
        json={"process_status": "resolved", "operator": "Bob", "note": "fixed"},
    )
    assert resolved.status_code == 200

    history = client.get(f"/api/v1/comments/{comment_id}/processing-history")
    assert history.status_code == 200
    assert len(history.json()) == 2

    copy = client.post(
        f"/api/v1/documents/{doc_id}/copy",
        json={"new_version_no": "2.0"},
    )
    assert copy.status_code == 201
    target_id = copy.json()["target_document_id"]

    target_clauses = client.get(f"/api/v1/documents/{target_id}/clauses")
    assert target_clauses.status_code == 200
    assert len(target_clauses.json()) == 2

    board = client.get(f"/api/v1/dashboard/documents/{doc_id}/risk")
    assert board.status_code == 200
    assert board.json()["resolved_by_risk"]["high"] == 1

    report = client.get("/api/v1/consistency/check")
    assert report.status_code == 200
    assert report.json()["passed"] is True

from fastapi.testclient import TestClient


def _create_doc_with_clause(client: TestClient, clause_no: str = "C1") -> tuple[int, int]:
    doc = client.post(
        "/api/v1/documents",
        json={"title": "Policy", "source_department": "Legal", "version_no": "1"},
    ).json()
    clause = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": clause_no, "clause_text": "Initial text"}]},
    ).json()[0]
    return doc["id"], clause["id"]


# ---------- 幂等导入：计数 + id_mapping ----------

def test_skip_existing_returns_skip_and_create_counts_with_mapping(
    client: TestClient,
) -> None:
    doc_id, existing_clause_id = _create_doc_with_clause(client, clause_no="C1")
    response = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "skip_existing",
            "clauses": [
                {"clause_no": "C1", "clause_text": "Updated text"},
                {"clause_no": "C2", "clause_text": "Brand new"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["created"] == 1
    assert data["skipped"] == 1
    assert data["updated"] == 0

    mapping = {m["clause_no"]: m for m in data["id_mapping"]}
    assert set(mapping.keys()) == {"C1", "C2"}
    assert mapping["C1"]["old_id"] == existing_clause_id
    assert mapping["C1"]["final_id"] == existing_clause_id
    assert mapping["C2"]["old_id"] is None
    assert mapping["C2"]["final_id"] != existing_clause_id

    c1 = next(c for c in data["clauses"] if c["clause_no"] == "C1")
    assert c1["clause_text"] == "Initial text"
    assert c1["id"] == existing_clause_id


def test_update_existing_returns_update_and_create_counts_with_mapping(
    client: TestClient,
) -> None:
    doc_id, existing_clause_id = _create_doc_with_clause(client, clause_no="C1")
    response = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {"clause_no": "C1", "clause_text": "Updated text"},
                {"clause_no": "C3", "clause_text": "Another new"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["created"] == 1
    assert data["updated"] == 1
    assert data["skipped"] == 0

    mapping = {m["clause_no"]: m for m in data["id_mapping"]}
    assert mapping["C1"]["old_id"] == existing_clause_id
    assert mapping["C1"]["final_id"] == existing_clause_id
    assert mapping["C3"]["old_id"] is None
    assert mapping["C3"]["final_id"] > 0

    c1 = next(c for c in data["clauses"] if c["clause_no"] == "C1")
    assert c1["clause_text"] == "Updated text"
    assert c1["id"] == existing_clause_id


def test_update_existing_does_not_resurrect_deprecated_clause(
    client: TestClient,
) -> None:
    doc_id, clause_id = _create_doc_with_clause(client)
    client.post(f"/api/v1/clauses/{clause_id}/deprecate")
    response = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [{"clause_no": "C1", "clause_text": "New text"}],
        },
    )
    assert response.status_code == 200
    c1 = next(c for c in response.json()["clauses"] if c["clause_no"] == "C1")
    assert c1["deprecated"] is True


# ---------- 废弃条款：写入被拒绝，历史仍可查 ----------

def test_deprecated_clause_blocks_new_comment_tag_binding_and_status_change(
    client: TestClient,
) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "high"},
    ).json()
    tag = client.post("/api/v1/risk-tags", json={"name": "Risk"}).json()

    client.post(f"/api/v1/clauses/{clause_id}/deprecate")

    add_resp = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "B", "comment_text": "No", "risk_level": "low"},
    )
    assert add_resp.status_code == 409
    assert add_resp.json()["error_code"] == "business_rule_violation"

    bind_resp = client.post(
        f"/api/v1/risk-tags/clauses/{clause_id}/bindings",
        json={"tag_id": tag["id"]},
    )
    assert bind_resp.status_code == 409

    status_resp = client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    assert status_resp.status_code == 409
    assert status_resp.json()["error_code"] == "business_rule_violation"


def test_deprecated_clause_history_still_queryable(client: TestClient) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead", "note": "ok"},
    )
    tag = client.post("/api/v1/risk-tags", json={"name": "Privacy"}).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause_id}/bindings",
        json={"tag_id": tag["id"]},
    )

    client.post(f"/api/v1/clauses/{clause_id}/deprecate")

    history = client.get(f"/api/v1/comments/{comment['id']}/processing-history")
    assert history.status_code == 200
    records = history.json()
    assert len(records) == 1
    assert records[0]["to_status"] == "accepted"

    bindings = client.get(f"/api/v1/risk-tags/clauses/{clause_id}/bindings")
    assert bindings.status_code == 200
    assert len(bindings.json()) == 1


# ---------- 状态机：rejected/resolved 不能回退 open ----------

def test_rejected_cannot_return_to_open(client: TestClient) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "rejected", "operator": "lead"},
    )
    response = client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "open", "operator": "lead"},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "invalid_state_transition"


def test_resolved_cannot_return_to_open(client: TestClient) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "high"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "resolved", "operator": "lead"},
    )
    response = client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "open", "operator": "lead"},
    )
    assert response.status_code == 409


def test_mandatory_transitions_write_complete_processing_records(
    client: TestClient,
) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "Alice", "comment_text": "Risk", "risk_level": "high"},
    ).json()

    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={
            "process_status": "accepted",
            "operator": "manager",
            "note": "acknowledged",
        },
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={
            "process_status": "resolved",
            "operator": "auditor",
            "note": "fixed",
        },
    )

    records = client.get(
        f"/api/v1/comments/{comment['id']}/processing-history"
    ).json()
    assert len(records) == 2

    first = records[0]
    assert first["from_status"] == "open"
    assert first["to_status"] == "accepted"
    assert first["operator"] == "manager"
    assert first["note"] == "acknowledged"
    assert first["action"] == "status_transition"
    assert "created_at" in first

    second = records[1]
    assert second["from_status"] == "accepted"
    assert second["to_status"] == "resolved"
    assert second["operator"] == "auditor"
    assert second["note"] == "fixed"


def test_no_duplicate_processing_record_on_non_mandatory_transition(
    client: TestClient,
) -> None:
    _doc_id, clause_id = _create_doc_with_clause(client)
    comment = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "medium"},
    ).json()
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "rejected", "operator": "lead"},
    )
    records = client.get(
        f"/api/v1/comments/{comment['id']}/processing-history"
    ).json()
    assert len(records) == 1
    assert records[0]["to_status"] == "accepted"

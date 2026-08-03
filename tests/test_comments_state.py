from fastapi.testclient import TestClient


def _setup_clause(client: TestClient) -> tuple[int, int]:
    doc_resp = client.post(
        "/api/v1/documents",
        json={"title": "Contract", "source_department": "Legal", "version_no": "1"},
    )
    doc_id = doc_resp.json()["id"]
    clause_resp = client.post(
        f"/api/v1/documents/{doc_id}/clauses/batch",
        json={"clauses": [{"clause_no": "C1", "clause_text": "Text"}]},
    )
    clause_id = clause_resp.json()[0]["id"]
    return doc_id, clause_id


def _add_comment(client: TestClient, clause_id: int, risk: str = "high") -> dict:
    response = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={
            "reviewer_name": "Reviewer",
            "comment_text": "Issue",
            "risk_level": risk,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_add_comment_to_deprecated_clause_rejected(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    client.post(f"/api/v1/clauses/{clause_id}/deprecate")
    response = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={
            "reviewer_name": "Bob",
            "comment_text": "Should fail",
            "risk_level": "low",
        },
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "business_rule_violation"


def test_invalid_risk_level_rejected(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    response = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={
            "reviewer_name": "Bob",
            "comment_text": "Bad",
            "risk_level": "extreme",
        },
    )
    assert response.status_code == 422


def test_open_to_accepted_creates_processing_record(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id)
    response = client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "manager", "note": "OK"},
    )
    assert response.status_code == 200
    history = client.get(f"/api/v1/comments/{comment['id']}/processing-history")
    assert history.status_code == 200
    records = history.json()
    assert len(records) == 1
    assert records[0]["from_status"] == "open"
    assert records[0]["to_status"] == "accepted"
    assert records[0]["operator"] == "manager"


def test_open_to_rejected_creates_processing_record(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id)
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "rejected", "operator": "lead"},
    )
    records = client.get(
        f"/api/v1/comments/{comment['id']}/processing-history"
    ).json()
    assert len(records) == 1
    assert records[0]["to_status"] == "rejected"


def test_accepted_to_resolved_creates_record(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id)
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    response = client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "resolved", "operator": "lead", "note": "done"},
    )
    assert response.status_code == 200
    records = client.get(
        f"/api/v1/comments/{comment['id']}/processing-history"
    ).json()
    assert len(records) == 2
    assert records[-1]["to_status"] == "resolved"


def test_resolved_cannot_roll_back(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id)
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
    assert response.json()["error_code"] == "invalid_state_transition"


def test_manual_processing_record(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id)
    response = client.post(
        f"/api/v1/comments/{comment['id']}/processing-records",
        json={"action": "investigate", "operator": "auditor", "note": "review"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["action"] == "investigate"
    assert data["from_status"] == "open"
    assert data["to_status"] == "open"


def test_query_unresolved_by_risk_level(client: TestClient) -> None:
    _doc_id, clause_id = _setup_clause(client)
    comment = _add_comment(client, clause_id, risk="critical")
    response = client.get(
        "/api/v1/comments/unresolved", params={"risk_level": "critical"}
    )
    assert response.status_code == 200
    data = response.json()
    assert any(c["id"] == comment["id"] for c in data)

    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "accepted", "operator": "lead"},
    )
    client.patch(
        f"/api/v1/comments/{comment['id']}/status",
        json={"process_status": "resolved", "operator": "lead"},
    )
    response_after = client.get(
        "/api/v1/comments/unresolved", params={"risk_level": "critical"}
    )
    assert all(c["id"] != comment["id"] for c in response_after.json())

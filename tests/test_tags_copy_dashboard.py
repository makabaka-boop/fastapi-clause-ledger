from fastapi.testclient import TestClient


def _make_document_with_clause(client: TestClient, deprecated: bool = False):
    doc = client.post(
        "/api/v1/documents",
        json={"title": "Agreement", "source_department": "Legal", "version_no": "1.0"},
    ).json()
    clause = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1", "clause_text": "Text"}]},
    ).json()[0]
    if deprecated:
        client.post(f"/api/v1/clauses/{clause['id']}/deprecate")
    return doc, clause


def test_create_and_bind_tag(client: TestClient) -> None:
    _doc, clause = _make_document_with_clause(client)
    tag = client.post(
        "/api/v1/risk-tags",
        json={"name": "GDPR", "description": "Privacy risk"},
    ).json()
    response = client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    assert response.status_code == 201
    assert response.json()["tag_id"] == tag["id"]


def test_bind_tag_to_deprecated_clause_rejected(client: TestClient) -> None:
    _doc, clause = _make_document_with_clause(client, deprecated=True)
    tag = client.post(
        "/api/v1/risk-tags", json={"name": "Legal", "description": ""}
    ).json()
    response = client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    assert response.status_code == 409


def test_duplicate_tag_binding_conflict(client: TestClient) -> None:
    _doc, clause = _make_document_with_clause(client)
    tag = client.post("/api/v1/risk-tags", json={"name": "IP"}).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    response = client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    assert response.status_code == 409


def test_document_version_copy(client: TestClient) -> None:
    doc, clause = _make_document_with_clause(client)
    tag = client.post("/api/v1/risk-tags", json={"name": "Privacy"}).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )

    open_comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "Open", "risk_level": "high"},
    ).json()
    resolved_comment = client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "B", "comment_text": "Closed", "risk_level": "low"},
    ).json()
    client.patch(
        f"/api/v1/comments/{resolved_comment['id']}/status",
        json={"process_status": "accepted", "operator": "x"},
    )
    client.patch(
        f"/api/v1/comments/{resolved_comment['id']}/status",
        json={"process_status": "resolved", "operator": "x"},
    )

    deprecated_clause = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "2", "clause_text": "Old"}]},
    ).json()[0]
    client.post(f"/api/v1/clauses/{deprecated_clause['id']}/deprecate")

    copy_resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "2.0"},
    )
    assert copy_resp.status_code == 201
    mapping = copy_resp.json()
    assert mapping["source_document_id"] == doc["id"]
    target_id = mapping["target_document_id"]

    target_clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    assert len(target_clauses) == 1
    assert target_clauses[0]["clause_no"] == "1"
    assert target_clauses[0]["latest_comment"]["comment_text"] == "Open"

    bindings = client.get(
        f"/api/v1/risk-tags/clauses/{target_clauses[0]['id']}/bindings"
    ).json()
    assert len(bindings) == 1
    assert bindings[0]["tag_id"] == tag["id"]

    mappings = client.get(
        f"/api/v1/documents/{doc['id']}/copy-mappings"
    ).json()
    assert len(mappings) == 1


def test_dashboard_summary(client: TestClient) -> None:
    doc, clause = _make_document_with_clause(client)
    client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "Risk", "risk_level": "critical"},
    )
    response = client.get(f"/api/v1/dashboard/documents/{doc['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_clauses"] == 1
    assert data["total_comments"] == 1
    assert data["open_comments"] == 1
    assert data["risk_distribution"]["critical"] == 1
    assert data["critical_unresolved"] == 1


def test_risk_distribution_by_tag(client: TestClient) -> None:
    doc, clause = _make_document_with_clause(client)
    tag = client.post("/api/v1/risk-tags", json={"name": "Security"}).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause['id']}/bindings",
        json={"tag_id": tag["id"]},
    )
    client.post(
        f"/api/v1/clauses/{clause['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "Issue", "risk_level": "high"},
    )
    response = client.get("/api/v1/dashboard/risk-distribution")
    assert response.status_code == 200
    items = response.json()
    security = next(i for i in items if i["tag_name"] == "Security")
    assert security["high"] == 1
    assert security["total"] == 1

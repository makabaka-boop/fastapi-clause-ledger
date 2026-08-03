from tests.helpers import add_comment, create_clauses, create_document, create_tag


def test_create_and_list_tags(client):
    t = create_tag(client, "privacy")
    assert t["name"] == "privacy"

    resp = client.get("/api/v1/tags")
    assert resp.status_code == 200
    assert any(x["name"] == "privacy" for x in resp.json())


def test_duplicate_tag_name(client):
    create_tag(client, "privacy")
    resp = client.post("/api/v1/tags", json={"name": "privacy"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "duplicate"


def test_bind_tag(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    tag = create_tag(client, "privacy")
    resp = client.post(
        "/api/v1/tags/bindings",
        json={"clause_id": 1, "tag_id": tag["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["clause_id"] == 1


def test_cannot_bind_deprecated_clause(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    tag = create_tag(client, "privacy")
    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")
    resp = client.post(
        "/api/v1/tags/bindings",
        json={"clause_id": 1, "tag_id": tag["id"]},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "business_rule_violation"


def test_risk_distribution(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2},
        {"clause_no": "1.2", "clause_text": "y", "clause_type": "t", "importance": 2},
    ])
    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})
    client.post("/api/v1/tags/bindings", json={"clause_id": 2, "tag_id": tag["id"]})
    add_comment(client, 1, risk="high")
    add_comment(client, 2, risk="low")

    resp = client.get(
        "/api/v1/tags/risk-distribution",
        params={"document_id": doc["id"]},
    )
    assert resp.status_code == 200
    dist = resp.json()
    assert len(dist) == 1
    assert dist[0]["high"] == 1
    assert dist[0]["low"] == 1
    assert dist[0]["total"] == 2

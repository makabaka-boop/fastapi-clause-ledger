from tests.helpers import (
    add_comment,
    create_clauses,
    create_document,
    create_tag,
)


def test_document_dashboard(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2},
        {"clause_no": "1.2", "clause_text": "y", "clause_type": "t", "importance": 2},
    ])
    client.post(f"/api/v1/documents/{doc['id']}/clauses/2/deprecate")

    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})
    add_comment(client, 1, risk="high")

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clauses"] == 2
    assert body["deprecated_clauses"] == 1
    assert body["active_clauses"] == 1
    assert body["total_comments"] == 1
    assert body["open_comments"] == 1
    assert body["risk_by_level"]["high"] == 1
    assert body["status_by_process"]["open"] == 1
    assert len(body["tag_distribution"]) == 1


def test_dashboard_not_found(client):
    resp = client.get("/api/v1/dashboard/documents/999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"

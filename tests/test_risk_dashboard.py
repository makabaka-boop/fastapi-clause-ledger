from tests.helpers import (
    add_comment,
    create_clauses,
    create_document,
    create_tag,
)


def _setup_document_with_risks(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "critical", "clause_type": "t", "importance": 5},
        {"clause_no": "1.2", "clause_text": "high", "clause_type": "t", "importance": 4},
        {"clause_no": "1.3", "clause_text": "low", "clause_type": "t", "importance": 1},
        {"clause_no": "1.4", "clause_text": "none", "clause_type": "t", "importance": 2},
    ])
    add_comment(client, 1, risk="critical", text="big issue")
    add_comment(client, 2, risk="high", text="medium issue")
    add_comment(client, 3, risk="low", text="small issue")
    return doc


def test_risk_dashboard_unresolved_and_resolved_counts(client):
    doc = _setup_document_with_risks(client)
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    assert resp.status_code == 200
    body = resp.json()

    assert body["document_id"] == doc["id"]
    assert body["include_deprecated"] is False

    unresolved = body["unresolved_by_risk"]
    assert unresolved["critical"] == 0
    assert unresolved["high"] == 1
    assert unresolved["low"] == 1
    assert unresolved["medium"] == 0
    assert unresolved["total"] == 2

    assert body["resolved_count"] == 1


def test_risk_dashboard_highest_risk_clauses_sorted(client):
    doc = _setup_document_with_risks(client)
    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    body = resp.json()

    highest = body["highest_risk_clauses"]
    assert len(highest) == 3
    assert highest[0]["clause_no"] == "1.1"
    assert highest[0]["highest_risk_level"] == "critical"
    assert highest[1]["clause_no"] == "1.2"
    assert highest[1]["highest_risk_level"] == "high"
    assert highest[2]["clause_no"] == "1.3"
    assert highest[2]["highest_risk_level"] == "low"

    assert highest[0]["latest_comment_text"] == "big issue"

    no_risk = {c["clause_no"] for c in highest}
    assert "1.4" not in no_risk


def test_risk_dashboard_tagged_clause_count(client):
    doc = _setup_document_with_risks(client)
    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})
    client.post("/api/v1/tags/bindings", json={"clause_id": 2, "tag_id": tag["id"]})

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    body = resp.json()
    assert body["tagged_clause_count"] == 2


def test_risk_dashboard_untagged_high_risk_clauses(client):
    doc = _setup_document_with_risks(client)
    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    body = resp.json()

    untagged = body["untagged_high_risk_clauses"]
    untagged_ids = {c["clause_no"] for c in untagged}
    assert "1.1" not in untagged_ids
    assert "1.2" in untagged_ids
    assert "1.3" not in untagged_ids


def test_risk_dashboard_excludes_deprecated_by_default(client):
    doc = _setup_document_with_risks(client)
    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    body = resp.json()

    assert body["unresolved_by_risk"]["critical"] == 0
    assert body["unresolved_by_risk"]["total"] == 2
    highest_nos = {c["clause_no"] for c in body["highest_risk_clauses"]}
    assert "1.1" not in highest_nos


def test_risk_dashboard_include_deprecated(client):
    doc = _setup_document_with_risks(client)
    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    resp = client.get(
        f"/api/v1/dashboard/documents/{doc['id']}/risk",
        params={"include_deprecated": "true"},
    )
    body = resp.json()
    assert body["include_deprecated"] is True
    assert body["unresolved_by_risk"]["critical"] == 1
    assert body["unresolved_by_risk"]["total"] == 3
    highest_nos = {c["clause_no"] for c in body["highest_risk_clauses"]}
    assert "1.1" in highest_nos


def test_risk_dashboard_resolved_not_in_unresolved(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 3},
    ])
    add_comment(client, 1, risk="critical")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    resp = client.get(f"/api/v1/dashboard/documents/{doc['id']}/risk")
    body = resp.json()
    assert body["unresolved_by_risk"]["total"] == 0
    assert body["unresolved_by_risk"]["critical"] == 0
    assert body["resolved_count"] == 1
    assert body["highest_risk_clauses"] == []


def test_risk_dashboard_not_found(client):
    resp = client.get("/api/v1/dashboard/documents/999/risk")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"

from tests.helpers import add_comment, create_clauses, create_document


def test_add_comment(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    c = add_comment(client, 1, risk="critical")
    assert c["process_status"] == "open"
    assert c["risk_level"] == "critical"
    assert c["created_at"].endswith("Z") or "+" in c["created_at"]


def test_invalid_risk_level(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    resp = client.post(
        "/api/v1/clauses/1/comments",
        json={"reviewer_name": "A", "comment_text": "x", "risk_level": "urgent"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


def test_cannot_comment_on_deprecated_clause(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")
    resp = client.post(
        "/api/v1/clauses/1/comments",
        json={"reviewer_name": "A", "comment_text": "x", "risk_level": "low"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "business_rule_violation"


def test_status_transition_writes_record(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "accepted", "note": "ok", "operator": "Bob"},
    )
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "accepted"

    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 1
    assert history[0]["from_status"] == "open"
    assert history[0]["to_status"] == "accepted"
    assert history[0]["operator"] == "Bob"


def test_cannot_transition_open_to_resolved(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)
    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "resolved", "note": "n"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_state_transition"


def test_open_to_rejected_writes_record(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)
    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "rejected", "note": "disagree", "operator": "Dan"},
    )
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "rejected"
    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 1
    assert history[0]["to_status"] == "rejected"

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "resolved", "note": "nope"},
    )
    assert resp.status_code == 409


def test_resolved_is_terminal(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "open", "note": "back"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "invalid_state_transition"
    assert body["details"]["terminal"] is True
    assert body["details"]["current_status"] == "resolved"

    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 2


def test_unresolved_by_risk(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2},
        {"clause_no": "1.2", "clause_text": "y", "clause_type": "t", "importance": 2},
    ])
    c1 = add_comment(client, 1, risk="high")
    add_comment(client, 2, risk="low")

    resp = client.get("/api/v1/comments/unresolved", params={"risk_level": "high"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == c1["id"]

    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})
    resp = client.get("/api/v1/comments/unresolved", params={"risk_level": "high"})
    assert resp.json() == []


def test_clauses_with_latest_comments(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, text="first", risk="low")
    add_comment(client, 1, text="second", risk="high")

    resp = client.get(
        f"/api/v1/documents/{doc['id']}/clauses/latest-comments"
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["latest_comment"]["comment_text"] == "second"


def test_deprecated_clause_rejects_open_comment_status_change(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    comment = add_comment(client, 1, risk="high")
    assert comment["process_status"] == "open"

    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "accepted", "note": "try", "operator": "Eve"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "business_rule_violation"
    assert "deprecated" in body["message"].lower()

    history = client.get("/api/v1/comments/1/process-records").json()
    assert history == []


def test_deprecated_clause_rejects_accepted_comment_status_change(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, risk="medium")
    client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "accepted", "note": "ok", "operator": "Bob"},
    )

    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "resolved", "note": "done", "operator": "Bob"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "business_rule_violation"


def test_deprecated_clause_history_still_queryable(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, reviewer="Alice", text="issue", risk="high")
    client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "rejected", "note": "disagree", "operator": "Dan"},
    )
    tag = client.post("/api/v1/tags", json={"name": "privacy"}).json()
    client.post(
        "/api/v1/tags/bindings",
        json={"clause_id": 1, "tag_id": tag["id"]},
    )

    client.post(f"/api/v1/documents/{doc['id']}/clauses/1/deprecate")

    comment = client.get("/api/v1/comments/1").json()
    assert comment["comment_text"] == "issue"
    assert comment["process_status"] == "rejected"

    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 1
    assert history[0]["from_status"] == "open"
    assert history[0]["to_status"] == "rejected"

    clauses = client.get(
        f"/api/v1/documents/{doc['id']}/clauses/latest-comments"
    ).json()
    assert len(clauses) == 1
    assert clauses[0]["deprecated"] is True
    assert clauses[0]["latest_comment"] is not None
    assert clauses[0]["latest_comment"]["reviewer_name"] == "Alice"


def test_rejected_cannot_return_to_open(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)
    client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "rejected", "note": "no", "operator": "Dan"},
    )

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "open", "note": "reopen", "operator": "Dan"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "invalid_state_transition"
    assert body["details"]["terminal"] is True
    assert body["details"]["current_status"] == "rejected"
    assert body["details"]["target_status"] == "open"


def test_process_record_integrity(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1, reviewer="Alice", text="risk", risk="critical")

    resp = client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "accepted", "note": "confirmed", "operator": "Bob"},
    )
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "accepted"

    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 1
    record = history[0]
    assert record["comment_id"] == 1
    assert record["from_status"] == "open"
    assert record["to_status"] == "accepted"
    assert record["note"] == "confirmed"
    assert record["operator"] == "Bob"
    assert "created_at" in record and record["created_at"]
    assert record["created_at"].endswith("Z") or "+" in record["created_at"]

    client.patch(
        "/api/v1/comments/1/status",
        json={"process_status": "resolved", "note": "fixed", "operator": "Carol"},
    )
    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 2
    assert history[1]["from_status"] == "accepted"
    assert history[1]["to_status"] == "resolved"
    assert history[1]["operator"] == "Carol"

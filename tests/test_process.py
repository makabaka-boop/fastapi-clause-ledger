from tests.helpers import add_comment, create_clauses, create_document


def test_manual_process_record(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    add_comment(client, 1)

    resp = client.post(
        "/api/v1/comments/1/process-records",
        json={"note": "investigating", "operator": "Carol"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_status"] == "open"
    assert body["to_status"] == "open"
    assert body["note"] == "investigating"

    history = client.get("/api/v1/comments/1/process-records").json()
    assert len(history) == 1


def test_process_record_comment_not_found(client):
    resp = client.post(
        "/api/v1/comments/999/process-records",
        json={"note": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"

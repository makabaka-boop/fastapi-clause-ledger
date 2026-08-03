from fastapi.testclient import TestClient


def create_document(
    client: TestClient,
    title: str = "NDA",
    version: str = "1.0",
    department: str = "Legal",
) -> dict:
    response = client.post(
        "/api/v1/documents",
        json={
            "title": title,
            "source_department": department,
            "version_no": version,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_document(client: TestClient) -> None:
    doc = create_document(client)
    assert doc["id"] > 0
    assert doc["document_status"] == "draft"
    assert doc["version_no"] == "1.0"
    assert "created_at" in doc


def test_create_duplicate_document_title_version_conflict(client: TestClient) -> None:
    create_document(client)
    response = client.post(
        "/api/v1/documents",
        json={"title": "NDA", "source_department": "Legal", "version_no": "1.0"},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "conflict"


def test_update_document_status(client: TestClient) -> None:
    doc = create_document(client)
    response = client.patch(
        f"/api/v1/documents/{doc['id']}/status",
        json={"document_status": "in_review"},
    )
    assert response.status_code == 200
    assert response.json()["document_status"] == "in_review"


def test_batch_create_clauses(client: TestClient) -> None:
    doc = create_document(client)
    response = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={
            "clauses": [
                {
                    "clause_no": "1.1",
                    "clause_text": "Confidentiality",
                    "clause_type": "obligation",
                    "importance": "high",
                },
                {
                    "clause_no": "1.2",
                    "clause_text": "Term",
                    "clause_type": "term",
                    "importance": "medium",
                },
            ]
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data) == 2
    assert data[0]["deprecated"] is False


def test_duplicate_clause_no_in_document_conflict(client: TestClient) -> None:
    doc = create_document(client)
    payload = {
        "clauses": [
            {"clause_no": "1.1", "clause_text": "A"},
            {"clause_no": "1.1", "clause_text": "B"},
        ]
    }
    response = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch", json=payload
    )
    assert response.status_code == 409


def test_idempotent_import_skip_existing(client: TestClient) -> None:
    doc = create_document(client)
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "Old text"}]},
    )
    response = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={
            "mode": "skip_existing",
            "clauses": [
                {"clause_no": "1.1", "clause_text": "New text"},
                {"clause_no": "1.2", "clause_text": "Brand new"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 1
    assert data["skipped"] == 1
    assert data["updated"] == 0
    clause_1_1 = next(c for c in data["clauses"] if c["clause_no"] == "1.1")
    assert clause_1_1["clause_text"] == "Old text"


def test_idempotent_import_update_existing(client: TestClient) -> None:
    doc = create_document(client)
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "Old text"}]},
    )
    response = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {"clause_no": "1.1", "clause_text": "Updated text"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["updated"] == 1
    assert data["created"] == 0
    assert data["clauses"][0]["clause_text"] == "Updated text"


def test_deprecate_clause(client: TestClient) -> None:
    doc = create_document(client)
    clause_resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "A"}]},
    )
    clause_id = clause_resp.json()[0]["id"]
    response = client.post(f"/api/v1/clauses/{clause_id}/deprecate")
    assert response.status_code == 200
    assert response.json()["deprecated"] is True


def test_list_clauses_with_latest_comment(client: TestClient) -> None:
    doc = create_document(client)
    clause_resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "A"}]},
    )
    clause_id = clause_resp.json()[0]["id"]
    client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={
            "reviewer_name": "Alice",
            "comment_text": "Risk identified",
            "risk_level": "high",
        },
    )
    response = client.get(f"/api/v1/documents/{doc['id']}/clauses")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["latest_comment"] is not None
    assert data[0]["latest_comment"]["reviewer_name"] == "Alice"

from tests.helpers import create_document


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_document(client):
    doc = create_document(client, title="NDA", version_no="v1.0")
    assert doc["id"] == 1
    assert doc["title"] == "NDA"
    assert doc["document_status"] == "draft"
    assert doc["created_at"].endswith("Z") or "T" in doc["created_at"]


def test_create_document_validation_error(client):
    resp = client.post(
        "/api/v1/documents",
        json={"title": "", "source_department": "Legal", "version_no": "v1"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert "details" in body


def test_update_document_status(client):
    doc = create_document(client)
    resp = client.patch(
        f"/api/v1/documents/{doc['id']}/status",
        json={"document_status": "in_review"},
    )
    assert resp.status_code == 200
    assert resp.json()["document_status"] == "in_review"


def test_get_document_not_found(client):
    resp = client.get("/api/v1/documents/999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "not_found"
    assert set(body.keys()) == {"error_code", "message", "details"}

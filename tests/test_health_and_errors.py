from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "fastapi-clause-ledger"
    assert "timestamp" in data


def test_error_response_format_for_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/documents/9999")
    assert response.status_code == 404
    data = response.json()
    assert set(data.keys()) == {"error_code", "message", "details"}
    assert data["error_code"] == "not_found"
    assert isinstance(data["details"], dict)


def test_validation_error_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        json={"title": "", "source_department": "Legal", "version_no": "1.0"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "validation_error"
    assert "errors" in data["details"]

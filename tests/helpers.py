def create_document(
    client,
    title="Contract",
    source_department="Legal",
    version_no="v1.0",
    document_status="draft",
):
    resp = client.post(
        "/api/v1/documents",
        json={
            "title": title,
            "source_department": source_department,
            "version_no": version_no,
            "document_status": document_status,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_clauses(client, document_id, clauses):
    resp = client.post(
        f"/api/v1/documents/{document_id}/clauses/batch",
        json={"clauses": clauses},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_tag(client, name="risk-tag"):
    resp = client.post("/api/v1/tags", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_comment(client, clause_id, reviewer="Alice", text="issue", risk="high"):
    resp = client.post(
        f"/api/v1/clauses/{clause_id}/comments",
        json={
            "reviewer_name": reviewer,
            "comment_text": text,
            "risk_level": risk,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()

from fastapi.testclient import TestClient


def _setup_document(client: TestClient) -> dict:
    doc = client.post(
        "/api/v1/documents",
        json={"title": "Master", "source_department": "Legal", "version_no": "1.0"},
    ).json()

    clauses_resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={
            "clauses": [
                {"clause_no": "1", "clause_text": "Confidentiality"},
                {"clause_no": "2", "clause_text": "Liability cap"},
            ]
        },
    ).json()
    clause_1 = clauses_resp[0]
    clause_2 = clauses_resp[1]

    tag_privacy = client.post(
        "/api/v1/risk-tags", json={"name": "Privacy", "description": ""}
    ).json()
    tag_finance = client.post(
        "/api/v1/risk-tags", json={"name": "Finance", "description": ""}
    ).json()
    client.post(
        f"/api/v1/risk-tags/clauses/{clause_1['id']}/bindings",
        json={"tag_id": tag_privacy["id"]},
    )
    client.post(
        f"/api/v1/risk-tags/clauses/{clause_2['id']}/bindings",
        json={"tag_id": tag_finance["id"]},
    )

    open_comment = client.post(
        f"/api/v1/clauses/{clause_1['id']}/comments",
        json={"reviewer_name": "A", "comment_text": "Open risk", "risk_level": "critical"},
    ).json()
    resolved_comment = client.post(
        f"/api/v1/clauses/{clause_1['id']}/comments",
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

    client.post(f"/api/v1/clauses/{clause_2['id']}/deprecate")

    return {
        "doc": doc,
        "clause_1": clause_1,
        "clause_2": clause_2,
        "tag_privacy": tag_privacy,
        "tag_finance": tag_finance,
        "open_comment": open_comment,
        "resolved_comment": resolved_comment,
    }


# ---------- 复制结果字段 ----------

def test_copy_returns_inheritance_summary(client: TestClient) -> None:
    data = _setup_document(client)
    doc_id = data["doc"]["id"]

    resp = client.post(
        f"/api/v1/documents/{doc_id}/copy",
        json={"new_version_no": "2.0"},
    )
    assert resp.status_code == 201, resp.text
    result = resp.json()

    assert result["source_document_id"] == doc_id
    assert result["target_document_id"] != doc_id
    assert result["skipped_deprecated_count"] == 1
    assert result["skipped_resolved_comment_count"] == 1
    assert result["copied_tag_count"] == 1

    assert len(result["clause_mappings"]) == 1
    mapping = result["clause_mappings"][0]
    assert mapping["source_clause_id"] == data["clause_1"]["id"]
    assert mapping["clause_no"] == "1"
    assert mapping["copied_comment_count"] == 1
    assert mapping["skipped_resolved_comment_count"] == 1
    inherited = {t["tag_name"] for t in mapping["inherited_tags"]}
    assert inherited == {"Privacy"}


def test_tag_inheritance_on_target(client: TestClient) -> None:
    data = _setup_document(client)
    copy = client.post(
        f"/api/v1/documents/{data['doc']['id']}/copy",
        json={"new_version_no": "2.0"},
    ).json()
    target_id = copy["target_document_id"]
    target_clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    assert len(target_clauses) == 1
    new_clause_id = target_clauses[0]["id"]

    bindings = client.get(
        f"/api/v1/risk-tags/clauses/{new_clause_id}/bindings"
    ).json()
    assert len(bindings) == 1
    assert bindings[0]["tag_id"] == data["tag_privacy"]["id"]


def test_resolved_comment_not_copied(client: TestClient) -> None:
    data = _setup_document(client)
    copy = client.post(
        f"/api/v1/documents/{data['doc']['id']}/copy",
        json={"new_version_no": "2.0"},
    ).json()
    target_id = copy["target_document_id"]
    target_clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    latest = target_clauses[0]["latest_comment"]
    assert latest is not None
    assert latest["comment_text"] == "Open risk"
    assert latest["process_status"] == "open"


def test_deprecated_clause_not_copied(client: TestClient) -> None:
    data = _setup_document(client)
    copy = client.post(
        f"/api/v1/documents/{data['doc']['id']}/copy",
        json={"new_version_no": "2.0"},
    ).json()
    target_id = copy["target_document_id"]
    target_clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    clause_nos = {c["clause_no"] for c in target_clauses}
    assert clause_nos == {"1"}


# ---------- 复制详情接口 ----------

def test_copy_detail_endpoint(client: TestClient) -> None:
    data = _setup_document(client)
    copy = client.post(
        f"/api/v1/documents/{data['doc']['id']}/copy",
        json={"new_version_no": "2.0"},
    ).json()
    target_id = copy["target_document_id"]

    detail = client.get(f"/api/v1/document-copies/{target_id}/detail")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["source_document_id"] == data["doc"]["id"]
    assert body["target_document_id"] == target_id
    assert len(body["clauses"]) == 1
    clause_detail = body["clauses"][0]
    assert clause_detail["source_clause_id"] == data["clause_1"]["id"]
    assert clause_detail["source_clause_text"] == "Confidentiality"
    assert clause_detail["target_clause_text"] == "Confidentiality"
    assert len(clause_detail["inherited_tags"]) == 1
    assert clause_detail["inherited_tags"][0]["tag_name"] == "Privacy"
    assert len(clause_detail["copied_comments"]) == 1
    assert clause_detail["copied_comments"][0]["comment_text"] == "Open risk"
    assert any("resolved" in r for r in clause_detail["skipped_reasons"])

    assert len(body["skipped_deprecated_clauses"]) == 1
    assert body["skipped_deprecated_clauses"][0]["clause_no"] == "2"
    assert body["skipped_deprecated_clauses"][0]["reason"] == "clause_deprecated"


# ---------- 风险看板口径 ----------

def test_risk_dashboard_counts_and_untagged(client: TestClient) -> None:
    data = _setup_document(client)
    doc_id = data["doc"]["id"]

    untagged_clause = client.post(
        f"/api/v1/documents/{doc_id}/clauses/batch",
        json={"clauses": [{"clause_no": "3", "clause_text": "No tags here"}]},
    ).json()[0]
    client.post(
        f"/api/v1/clauses/{untagged_clause['id']}/comments",
        json={"reviewer_name": "C", "comment_text": "High risk no tag", "risk_level": "high"},
    )

    resp = client.get(f"/api/v1/dashboard/documents/{doc_id}/risk")
    assert resp.status_code == 200, resp.text
    board = resp.json()

    assert board["document_id"] == doc_id
    assert board["include_deprecated"] is False
    assert board["total_clauses"] == 2
    assert board["tagged_clause_count"] == 1
    assert board["untagged_clause_count"] == 1

    assert board["unresolved_by_risk"]["critical"] == 1
    assert board["unresolved_by_risk"]["high"] == 1
    assert board["resolved_by_risk"]["low"] == 1
    assert board["total_unresolved"] == 2
    assert board["total_resolved"] == 1

    top_nos = {c["clause_no"] for c in board["top_risk_clauses"]}
    assert "1" in top_nos

    untagged_high = {c["clause_no"] for c in board["untagged_high_risk_clauses"]}
    assert untagged_high == {"3"}


def test_risk_dashboard_resolved_excluded_from_unresolved(client: TestClient) -> None:
    data = _setup_document(client)
    doc_id = data["doc"]["id"]
    board = client.get(
        f"/api/v1/dashboard/documents/{doc_id}/risk"
    ).json()
    assert board["unresolved_by_risk"]["low"] == 0
    assert board["resolved_by_risk"]["low"] == 1


def test_risk_dashboard_deprecated_excluded_by_default(
    client: TestClient,
) -> None:
    data = _setup_document(client)
    doc_id = data["doc"]["id"]
    board_default = client.get(
        f"/api/v1/dashboard/documents/{doc_id}/risk"
    ).json()
    assert board_default["total_clauses"] == 1
    assert all(
        c["clause_no"] != "2" for c in board_default["top_risk_clauses"]
    )

    board_inclusive = client.get(
        f"/api/v1/dashboard/documents/{doc_id}/risk",
        params={"include_deprecated": "true"},
    ).json()
    assert board_inclusive["total_clauses"] == 2
    assert board_inclusive["include_deprecated"] is True

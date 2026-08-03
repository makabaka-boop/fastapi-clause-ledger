def test_readme_end_to_end_flow(client):
    base = "/api/v1"

    doc = client.post(
        f"{base}/documents",
        json={
            "title": "Master Service Agreement",
            "source_department": "Legal",
            "version_no": "v1.0",
        },
    )
    assert doc.status_code == 201
    doc_id = doc.json()["id"]

    client.patch(
        f"{base}/documents/{doc_id}/status",
        json={"document_status": "in_review"},
    )

    import_resp = client.post(
        f"{base}/documents/{doc_id}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {
                    "clause_no": "1.1",
                    "clause_text": "Party A shall indemnify Party B.",
                    "clause_type": "indemnity",
                    "importance": 5,
                },
                {
                    "clause_no": "2.1",
                    "clause_text": "Agreement governed by local law.",
                    "clause_type": "governing_law",
                    "importance": 3,
                },
            ],
        },
    )
    assert import_resp.status_code == 201
    import_body = import_resp.json()
    assert import_body["created"] == 2
    assert len(import_body["id_mappings"]) == 2

    comment = client.post(
        f"{base}/clauses/1/comments",
        json={
            "reviewer_name": "Alice",
            "comment_text": "Indemnity cap is missing.",
            "risk_level": "high",
        },
    )
    assert comment.status_code == 201
    comment_id = comment.json()["id"]
    assert comment.json()["process_status"] == "open"

    tag = client.post(f"{base}/tags", json={"name": "indemnity-risk"})
    assert tag.status_code == 201
    tag_id = tag.json()["id"]

    bind = client.post(
        f"{base}/tags/bindings",
        json={"clause_id": 1, "tag_id": tag_id},
    )
    assert bind.status_code == 201

    accepted = client.patch(
        f"{base}/comments/{comment_id}/status",
        json={"process_status": "accepted", "note": "Will add cap", "operator": "Bob"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["process_status"] == "accepted"

    resolved = client.patch(
        f"{base}/comments/{comment_id}/status",
        json={"process_status": "resolved", "note": "Cap added", "operator": "Bob"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["process_status"] == "resolved"

    history = client.get(f"{base}/comments/{comment_id}/process-records")
    assert history.status_code == 200
    records = history.json()
    assert len(records) == 2
    assert records[0]["from_status"] == "open"
    assert records[0]["to_status"] == "accepted"
    assert records[1]["from_status"] == "accepted"
    assert records[1]["to_status"] == "resolved"

    copy = client.post(
        f"{base}/documents/{doc_id}/copy",
        json={"new_version_no": "v2.0", "copied_by": "Alice"},
    )
    assert copy.status_code == 201
    copy_body = copy.json()
    target_id = copy_body["target_document_id"]
    assert copy_body["copied_clauses"] == 2
    assert copy_body["copied_tag_count"] == 1

    target_clauses = client.get(f"{base}/documents/{target_id}/clauses")
    assert target_clauses.status_code == 200
    assert len(target_clauses.json()) == 2

    target_latest = client.get(
        f"{base}/documents/{target_id}/clauses/latest-comments"
    )
    assert target_latest.status_code == 200
    for clause in target_latest.json():
        assert clause["latest_comment"] is None

    risk_dash = client.get(f"{base}/dashboard/documents/{doc_id}/risk")
    assert risk_dash.status_code == 200
    dash = risk_dash.json()
    assert dash["resolved_count"] == 1
    assert dash["tagged_clause_count"] == 1

    detail = client.get(f"{base}/documents/{target_id}/copy-detail")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert len(detail_body["copied_clauses"]) == 2
    inherited = [
        c for c in detail_body["copied_clauses"] if c["clause_no"] == "1.1"
    ][0]
    assert len(inherited["inherited_tags"]) == 1
    assert inherited["source_resolved_comment_count"] == 1

    consistency = client.get(f"{base}/consistency/check")
    assert consistency.status_code == 200
    report = consistency.json()
    assert "checks" in report
    assert "all_passed" in report
    assert isinstance(report["checks"], list)
    assert len(report["checks"]) == 7

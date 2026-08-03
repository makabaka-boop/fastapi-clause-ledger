from tests.helpers import (
    add_comment,
    create_clauses,
    create_document,
    create_tag,
)


def test_copy_document_skips_deprecated_and_copies_tags(client):
    doc = create_document(client, version_no="v1.0")
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "active", "clause_type": "t", "importance": 2},
        {"clause_no": "1.2", "clause_text": "old", "clause_type": "t", "importance": 2},
    ])
    client.post(f"/api/v1/documents/{doc['id']}/clauses/2/deprecate")

    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})
    client.post("/api/v1/tags/bindings", json={"clause_id": 2, "tag_id": tag["id"]})

    add_comment(client, 1, risk="high")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2.0", "copied_by": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_document_id"] == doc["id"]
    assert body["copied_clauses"] == 1
    assert body["copied_tag_count"] == 1
    assert body["skipped_deprecated_count"] == 1
    assert body["skipped_resolved_comment_count"] == 1

    assert len(body["clause_mappings"]) == 1
    mapping = body["clause_mappings"][0]
    assert mapping["source_clause_id"] == 1
    assert mapping["target_clause_id"] != 1
    assert mapping["clause_no"] == "1.1"
    assert mapping["copied_tag_ids"] == [tag["id"]]

    target_id = body["target_document_id"]

    target = client.get(f"/api/v1/documents/{target_id}").json()
    assert target["version_no"] == "v2.0"

    clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    assert len(clauses) == 1
    assert clauses[0]["clause_no"] == "1.1"
    assert clauses[0]["deprecated"] is False

    target_comments = client.get(
        f"/api/v1/documents/{target_id}/clauses/latest-comments"
    ).json()
    assert target_comments[0]["latest_comment"] is None


def test_copy_tag_inheritance_with_multiple_tags(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "a", "clause_type": "t", "importance": 3},
        {"clause_no": "1.2", "clause_text": "b", "clause_type": "t", "importance": 1},
    ])
    privacy = create_tag(client, "privacy")
    finance = create_tag(client, "finance")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": privacy["id"]})
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": finance["id"]})
    client.post("/api/v1/tags/bindings", json={"clause_id": 2, "tag_id": finance["id"]})

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2.0"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["copied_clauses"] == 2
    assert body["copied_tag_count"] == 3
    assert body["skipped_deprecated_count"] == 0
    assert body["skipped_resolved_comment_count"] == 0

    mappings = {m["clause_no"]: m for m in body["clause_mappings"]}
    assert set(mappings["1.1"]["copied_tag_ids"]) == {privacy["id"], finance["id"]}
    assert mappings["1.2"]["copied_tag_ids"] == [finance["id"]]


def test_copy_does_not_copy_resolved_or_unresolved_comments(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "a", "clause_type": "t", "importance": 2},
    ])
    add_comment(client, 1, reviewer="Alice", text="resolved risk", risk="high")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})
    add_comment(client, 1, reviewer="Bob", text="open risk", risk="medium")

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2.0"},
    )
    body = resp.json()
    assert body["skipped_resolved_comment_count"] == 1

    target_id = body["target_document_id"]
    target_clauses = client.get(
        f"/api/v1/documents/{target_id}/clauses"
    ).json()
    assert len(target_clauses) == 1

    target_comments = client.get(
        f"/api/v1/documents/{target_id}/clauses/latest-comments"
    ).json()
    assert target_comments[0]["latest_comment"] is None


def test_copy_result_detail_endpoint(client):
    doc = create_document(client, version_no="v1.0")
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "active", "clause_type": "obligation", "importance": 3},
        {"clause_no": "1.2", "clause_text": "old", "clause_type": "right", "importance": 2},
    ])
    client.post(f"/api/v1/documents/{doc['id']}/clauses/2/deprecate")

    tag = create_tag(client, "privacy")
    client.post("/api/v1/tags/bindings", json={"clause_id": 1, "tag_id": tag["id"]})

    add_comment(client, 1, risk="critical")
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "accepted", "note": "ok"})
    client.patch("/api/v1/comments/1/status",
                 json={"process_status": "resolved", "note": "done"})

    copy_resp = client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2.0"},
    )
    target_id = copy_resp.json()["target_document_id"]

    resp = client.get(f"/api/v1/documents/{target_id}/copy-detail")
    assert resp.status_code == 200
    detail = resp.json()

    assert detail["source_document_id"] == doc["id"]
    assert detail["target_document_id"] == target_id
    assert "copy_mapping_id" in detail

    assert len(detail["copied_clauses"]) == 1
    copied = detail["copied_clauses"][0]
    assert copied["source_clause_id"] == 1
    assert copied["clause_no"] == "1.1"
    assert copied["clause_text"] == "active"
    assert copied["clause_type"] == "obligation"
    assert copied["importance"] == 3
    assert len(copied["inherited_tags"]) == 1
    assert copied["inherited_tags"][0]["tag_name"] == "privacy"
    assert copied["source_resolved_comment_count"] == 1

    assert len(detail["skipped_clauses"]) == 1
    skipped = detail["skipped_clauses"][0]
    assert skipped["source_clause_id"] == 2
    assert skipped["clause_no"] == "1.2"
    assert skipped["reason"] == "deprecated"

    assert detail["summary"]["copied_clauses"] == 1
    assert detail["summary"]["skipped_deprecated_count"] == 1
    assert detail["summary"]["copied_tag_count"] == 1
    assert detail["summary"]["skipped_resolved_comment_count"] == 1


def test_copy_mapping_query(client):
    doc = create_document(client)
    create_clauses(client, doc["id"], [
        {"clause_no": "1.1", "clause_text": "x", "clause_type": "t", "importance": 2}
    ])
    client.post(
        f"/api/v1/documents/{doc['id']}/copy",
        json={"new_version_no": "v2.0"},
    )

    resp = client.get("/api/v1/copy-mappings")
    assert resp.status_code == 200
    mappings = resp.json()
    assert len(mappings) == 1
    assert mappings[0]["source_document_id"] == doc["id"]
    assert len(mappings[0]["clause_mappings"]) == 1

    by_source = client.get(
        "/api/v1/copy-mappings",
        params={"source_document_id": doc["id"]},
    ).json()
    assert len(by_source) == 1

    single = client.get(f"/api/v1/copy-mappings/{mappings[0]['id']}").json()
    assert single["id"] == mappings[0]["id"]


def test_copy_source_not_found(client):
    resp = client.post(
        "/api/v1/documents/999/copy",
        json={"new_version_no": "v2.0"},
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


def test_copy_detail_not_found_for_non_copied_document(client):
    doc = create_document(client)
    resp = client.get(f"/api/v1/documents/{doc['id']}/copy-detail")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"

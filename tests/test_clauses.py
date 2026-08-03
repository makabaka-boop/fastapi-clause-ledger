from tests.helpers import create_document


def _clause(no, text="text", ctype="obligation", importance=2):
    return {
        "clause_no": no,
        "clause_text": text,
        "clause_type": ctype,
        "importance": importance,
    }


def test_batch_create_clauses(client):
    doc = create_document(client)
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1"), _clause("1.2")]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 2
    assert len(body["clause_ids"]) == 2


def test_duplicate_clause_no_in_batch(client):
    doc = create_document(client)
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1"), _clause("1.1")]},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "duplicate"


def test_duplicate_clause_no_across_requests(client):
    doc = create_document(client)
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1")]},
    )
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1")]},
    )
    assert resp.status_code == 409


def test_import_skip_existing(client):
    doc = create_document(client)
    first = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1", text="old")]},
    ).json()
    existing_id = first["clause_ids"][0]

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={
            "mode": "skip_existing",
            "clauses": [_clause("1.1", text="new"), _clause("1.2")],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
    assert body["updated"] == 0

    mappings = {m["clause_no"]: m for m in body["id_mappings"]}
    assert set(mappings.keys()) == {"1.1", "1.2"}

    assert mappings["1.1"]["action"] == "skipped"
    assert mappings["1.1"]["old_clause_id"] == existing_id
    assert mappings["1.1"]["final_clause_id"] == existing_id

    assert mappings["1.2"]["action"] == "created"
    assert mappings["1.2"]["old_clause_id"] is None
    new_id = mappings["1.2"]["final_clause_id"]
    assert new_id != existing_id

    clauses = client.get(
        f"/api/v1/documents/{doc['id']}/clauses"
    ).json()
    c11 = next(c for c in clauses if c["clause_no"] == "1.1")
    assert c11["clause_text"] == "old"
    assert c11["id"] == existing_id


def test_import_update_existing(client):
    doc = create_document(client)
    first = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1", text="old")]},
    ).json()
    existing_id = first["clause_ids"][0]

    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [_clause("1.1", text="new"), _clause("1.2")],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["skipped"] == 0

    mappings = {m["clause_no"]: m for m in body["id_mappings"]}
    assert mappings["1.1"]["action"] == "updated"
    assert mappings["1.1"]["old_clause_id"] == existing_id
    assert mappings["1.1"]["final_clause_id"] == existing_id

    assert mappings["1.2"]["action"] == "created"
    assert mappings["1.2"]["old_clause_id"] is None

    clauses = client.get(
        f"/api/v1/documents/{doc['id']}/clauses"
    ).json()
    c11 = next(c for c in clauses if c["clause_no"] == "1.1")
    assert c11["clause_text"] == "new"
    assert c11["id"] == existing_id


def test_import_invalid_mode(client):
    doc = create_document(client)
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={"mode": "bogus", "clauses": [_clause("1.1")]},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


def test_deprecate_clause(client):
    doc = create_document(client)
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [_clause("1.1")]},
    )
    resp = client.post(
        f"/api/v1/documents/{doc['id']}/clauses/1/deprecate"
    )
    assert resp.status_code == 200
    assert resp.json()["deprecated"] is True

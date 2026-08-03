"""End-to-end API tests covering the spec's rules and endpoints."""


def _make_document(client, **overrides):
    payload = {
        "title": "Vendor MSA",
        "source_department": "Legal",
        "version_no": "v1",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/documents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_clause(client, document_id, clause_no="C-1", **overrides):
    payload = {
        "clause_no": clause_no,
        "clause_text": "The vendor shall indemnify...",
        "clause_type": "obligation",
        "importance": "high",
    }
    payload.update(overrides)
    resp = client.post(f"/api/v1/documents/{document_id}/clauses",
                       json={"clauses": [payload]})
    assert resp.status_code == 201, resp.text
    return resp.json()[0]


def _add_review(client, clause_id, risk_level="high"):
    resp = client.post(
        f"/api/v1/clauses/{clause_id}/reviews",
        json={
            "reviewer_name": "Alice",
            "comment_text": "Needs a liability cap.",
            "risk_level": risk_level,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Health & documents
# ---------------------------------------------------------------------------
def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_update_document_status(client):
    doc = _make_document(client)
    assert doc["document_status"] == "draft"
    assert "T" in doc["created_at"]  # ISO 8601

    resp = client.patch(f"/api/v1/documents/{doc['id']}/status",
                        json={"document_status": "under_review"})
    assert resp.status_code == 200
    assert resp.json()["document_status"] == "under_review"


def test_invalid_document_status_uses_error_envelope(client):
    resp = client.post("/api/v1/documents", json={
        "title": "X", "source_department": "Legal",
        "version_no": "v1", "document_status": "bogus",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert set(body) == {"error_code", "message", "details"}
    assert body["error_code"] == "validation_error"


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
def test_duplicate_clause_no_rejected(client):
    doc = _make_document(client)
    _add_clause(client, doc["id"], clause_no="C-1")
    resp = client.post(f"/api/v1/documents/{doc['id']}/clauses",
                       json={"clauses": [{"clause_no": "C-1",
                                          "clause_text": "dup",
                                          "clause_type": "other",
                                          "importance": "low"}]})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "conflict"


def test_duplicate_clause_no_within_batch_rejected(client):
    doc = _make_document(client)
    resp = client.post(f"/api/v1/documents/{doc['id']}/clauses", json={
        "clauses": [
            {"clause_no": "C-1", "clause_text": "a", "clause_type": "other",
             "importance": "low"},
            {"clause_no": "C-1", "clause_text": "b", "clause_type": "other",
             "importance": "low"},
        ]
    })
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


def test_idempotent_import_skip_existing(client):
    doc = _make_document(client)
    orig = _add_clause(client, doc["id"], clause_no="C-1", clause_text="orig")
    resp = client.post(f"/api/v1/documents/{doc['id']}/clauses/import", json={
        "mode": "skip_existing",
        "clauses": [
            {"clause_no": "C-1", "clause_text": "changed", "clause_type": "other",
             "importance": "low"},
            {"clause_no": "C-2", "clause_text": "new", "clause_type": "other",
             "importance": "low"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert [c["clause_no"] for c in body["created"]] == ["C-2"]
    assert body["skipped"] == ["C-1"]
    assert body["updated"] == []
    # counts must be reported explicitly
    assert body["skipped_count"] == 1
    assert body["created_count"] == 1
    assert body["updated_count"] == 0
    # skipped clause keeps its original text and its old id maps to itself
    clauses = client.get(f"/api/v1/documents/{doc['id']}/clauses").json()
    c1 = next(c["clause"] for c in clauses if c["clause"]["clause_no"] == "C-1")
    assert c1["clause_text"] == "orig"
    skip_map = next(m for m in body["mapping"] if m["clause_no"] == "C-1")
    assert skip_map["action"] == "skipped"
    assert skip_map["previous_clause_id"] == orig["id"] == skip_map["final_clause_id"]
    create_map = next(m for m in body["mapping"] if m["clause_no"] == "C-2")
    assert create_map["action"] == "created"
    assert create_map["previous_clause_id"] is None


def test_idempotent_import_update_existing(client):
    doc = _make_document(client)
    orig = _add_clause(client, doc["id"], clause_no="C-1", clause_text="orig")
    resp = client.post(f"/api/v1/documents/{doc['id']}/clauses/import", json={
        "mode": "update_existing",
        "clauses": [
            {"clause_no": "C-1", "clause_text": "changed", "clause_type": "right",
             "importance": "low"},
            {"clause_no": "C-2", "clause_text": "brand new", "clause_type": "other",
             "importance": "low"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"][0]["clause_text"] == "changed"
    assert body["updated"][0]["clause_type"] == "right"
    # counts must be reported explicitly
    assert body["updated_count"] == 1
    assert body["created_count"] == 1
    assert body["skipped_count"] == 0
    # updated clause reuses its row: old id == final id
    upd_map = next(m for m in body["mapping"] if m["clause_no"] == "C-1")
    assert upd_map["action"] == "updated"
    assert upd_map["previous_clause_id"] == orig["id"] == upd_map["final_clause_id"]


def test_import_is_idempotent_when_repeated(client):
    doc = _make_document(client)
    payload = {
        "mode": "skip_existing",
        "clauses": [
            {"clause_no": "C-1", "clause_text": "a", "clause_type": "other",
             "importance": "low"},
        ],
    }
    first = client.post(f"/api/v1/documents/{doc['id']}/clauses/import",
                        json=payload).json()
    assert first["created_count"] == 1 and first["skipped_count"] == 0
    final_id = first["mapping"][0]["final_clause_id"]

    second = client.post(f"/api/v1/documents/{doc['id']}/clauses/import",
                         json=payload).json()
    # nothing new is created; same row is reported as skipped
    assert second["created_count"] == 0 and second["skipped_count"] == 1
    assert second["mapping"][0]["final_clause_id"] == final_id


def test_import_invalid_mode_rejected(client):
    doc = _make_document(client)
    resp = client.post(f"/api/v1/documents/{doc['id']}/clauses/import", json={
        "mode": "overwrite_all",
        "clauses": [{"clause_no": "C-1", "clause_text": "x",
                     "clause_type": "other", "importance": "low"}],
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deprecation guards
# ---------------------------------------------------------------------------
def test_deprecated_clause_rejects_review_and_tag(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    tag = client.post("/api/v1/risk-tags",
                      json={"name": "GDPR"}).json()

    dep = client.post(f"/api/v1/clauses/{clause['id']}/deprecate")
    assert dep.status_code == 200
    assert dep.json()["deprecated"] is True

    r = client.post(f"/api/v1/clauses/{clause['id']}/reviews", json={
        "reviewer_name": "Bob", "comment_text": "late", "risk_level": "low"})
    assert r.status_code == 409
    assert r.json()["error_code"] == "rule_violation"

    b = client.post(f"/api/v1/clauses/{clause['id']}/tags",
                    json={"tag_id": tag["id"]})
    assert b.status_code == 409
    assert b.json()["error_code"] == "rule_violation"


def test_deprecation_preserves_history_but_freezes_open_opinion(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    # bind a tag and add an opinion BEFORE deprecation
    tag = client.post("/api/v1/risk-tags", json={"name": "SOX"}).json()
    client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]})
    review = _add_review(client, clause["id"])

    dep = client.post(f"/api/v1/clauses/{clause['id']}/deprecate")
    assert dep.status_code == 200

    # history is still queryable: latest opinion and tag binding remain visible
    rows = client.get(f"/api/v1/documents/{doc['id']}/clauses").json()
    frozen = next(r for r in rows if r["clause"]["id"] == clause["id"])
    assert frozen["clause"]["deprecated"] is True
    assert frozen["latest_review"]["id"] == review["id"]
    dist = client.get(f"/api/v1/risk-tags/{tag['id']}/risk-distribution").json()
    assert dist["total_reviews"] == 1  # historical binding still counts

    # changing the still-open opinion is rejected
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "accepted", "operator": "A"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "rule_violation"

    # the explicit process-record endpoint is blocked too
    resp = client.post(f"/api/v1/reviews/{review['id']}/process-records", json={
        "from_status": "open", "to_status": "rejected", "operator": "A"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "rule_violation"


def test_in_flight_opinion_can_finish_after_deprecation(client):
    """An opinion already 'accepted' before deprecation can still be resolved."""
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "accepted", "operator": "A"})

    client.post(f"/api/v1/clauses/{clause['id']}/deprecate")

    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "resolved", "operator": "A"})
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "resolved"


# ---------------------------------------------------------------------------
# Review state machine
# ---------------------------------------------------------------------------
def test_status_transition_requires_process_record(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])

    # open -> accepted without operator is rejected
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "accepted"})
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"

    # with operator it succeeds and journals a record
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "accepted", "operator": "Alice"})
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "accepted"

    hist = client.get(f"/api/v1/reviews/{review['id']}/process-records").json()
    assert len(hist) == 1
    assert hist[0]["from_status"] == "open"
    assert hist[0]["to_status"] == "accepted"


def test_full_lifecycle_to_resolved(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])

    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "accepted", "operator": "A"})
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "resolved", "operator": "A"})
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "resolved"


def test_no_rollback_from_resolved(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "accepted", "operator": "A"})
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "resolved", "operator": "A"})
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "open", "operator": "A"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_transition"


def test_no_rollback_from_rejected(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "rejected", "operator": "A"})
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "open", "operator": "A"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_transition"


def test_illegal_transition_open_to_resolved(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    resp = client.patch(f"/api/v1/reviews/{review['id']}/status",
                       json={"to_status": "resolved", "operator": "A"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_transition"


def test_explicit_process_record_endpoint(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    resp = client.post(f"/api/v1/reviews/{review['id']}/process-records", json={
        "from_status": "open", "to_status": "rejected", "operator": "Q",
        "note": "not applicable"})
    assert resp.status_code == 201
    assert client.get(f"/api/v1/reviews/{review['id']}/process-records"
                      ).json()[0]["to_status"] == "rejected"


def test_process_record_write_completeness(client):
    """Every status change journals a complete, ordered record."""
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])

    r1 = client.patch(f"/api/v1/reviews/{review['id']}/status",
                     json={"to_status": "accepted", "operator": "Alice",
                           "note": "cap agreed"})
    assert r1.status_code == 200
    r2 = client.patch(f"/api/v1/reviews/{review['id']}/status",
                     json={"to_status": "resolved", "operator": "Bob",
                           "note": "signed off"})
    assert r2.status_code == 200

    history = client.get(f"/api/v1/reviews/{review['id']}/process-records").json()
    assert len(history) == 2
    # ordered oldest -> newest, chained from/to statuses, full field set
    first, second = history
    assert (first["from_status"], first["to_status"]) == ("open", "accepted")
    assert first["operator"] == "Alice" and first["note"] == "cap agreed"
    assert (second["from_status"], second["to_status"]) == ("accepted", "resolved")
    assert second["operator"] == "Bob" and second["note"] == "signed off"
    for record in history:
        assert record["review_id"] == review["id"]
        assert "T" in record["created_at"]  # ISO 8601 timestamp present


def test_process_record_from_status_must_match_current(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    review = _add_review(client, clause["id"])
    # review is 'open'; claiming from_status 'accepted' is rejected
    resp = client.post(f"/api/v1/reviews/{review['id']}/process-records", json={
        "from_status": "accepted", "to_status": "resolved", "operator": "Q"})
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"
    # and no partial record leaked into history
    assert client.get(f"/api/v1/reviews/{review['id']}/process-records").json() == []


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def test_clauses_with_latest_review(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    _add_review(client, clause["id"], risk_level="low")
    latest = _add_review(client, clause["id"], risk_level="critical")

    rows = client.get(f"/api/v1/documents/{doc['id']}/clauses").json()
    assert len(rows) == 1
    assert rows[0]["latest_review"]["id"] == latest["id"]
    assert rows[0]["latest_review"]["risk_level"] == "critical"


def test_unprocessed_by_risk(client):
    doc = _make_document(client)
    c1 = _add_clause(client, doc["id"], clause_no="C-1")
    c2 = _add_clause(client, doc["id"], clause_no="C-2")
    _add_review(client, c1["id"], risk_level="high")
    r2 = _add_review(client, c2["id"], risk_level="high")
    # resolve r2 so it drops out of the "unprocessed" list
    client.patch(f"/api/v1/reviews/{r2['id']}/status",
                json={"to_status": "accepted", "operator": "A"})

    rows = client.get("/api/v1/reviews/unprocessed?risk_level=high").json()
    assert [r["clause_id"] for r in rows] == [c1["id"]]


def test_tag_risk_distribution(client):
    doc = _make_document(client)
    clause = _add_clause(client, doc["id"])
    tag = client.post("/api/v1/risk-tags", json={"name": "PII"}).json()
    client.post(f"/api/v1/clauses/{clause['id']}/tags",
               json={"tag_id": tag["id"]})
    _add_review(client, clause["id"], risk_level="high")
    _add_review(client, clause["id"], risk_level="high")

    dist = client.get(f"/api/v1/risk-tags/{tag['id']}/risk-distribution").json()
    assert dist["total_reviews"] == 2
    assert dist["distribution"][0]["risk_level"] == "high"
    assert dist["distribution"][0]["count"] == 2


def test_risk_dashboard(client):
    doc = _make_document(client)
    c1 = _add_clause(client, doc["id"], clause_no="C-1")
    c2 = _add_clause(client, doc["id"], clause_no="C-2")
    _add_review(client, c1["id"], risk_level="high")
    client.post(f"/api/v1/clauses/{c2['id']}/deprecate")

    dash = client.get(f"/api/v1/documents/{doc['id']}/dashboard").json()
    assert dash["total_clauses"] == 2
    assert dash["active_clauses"] == 1
    assert dash["deprecated_clauses"] == 1
    assert dash["total_reviews"] == 1
    assert dash["open_reviews"] == 1


# ---------------------------------------------------------------------------
# Document copy
# ---------------------------------------------------------------------------
def test_copy_document_only_active_clauses_and_tags(client):
    doc = _make_document(client)
    active = _add_clause(client, doc["id"], clause_no="C-1")
    dep = _add_clause(client, doc["id"], clause_no="C-2")
    tag = client.post("/api/v1/risk-tags", json={"name": "AML"}).json()
    client.post(f"/api/v1/clauses/{active['id']}/tags",
               json={"tag_id": tag["id"]})
    # add a review then resolve it — must NOT be copied
    review = _add_review(client, active["id"])
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "accepted", "operator": "A"})
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "resolved", "operator": "A"})
    client.post(f"/api/v1/clauses/{dep['id']}/deprecate")

    resp = client.post(f"/api/v1/documents/{doc['id']}/copies",
                      json={"version_no": "v2"})
    assert resp.status_code == 201
    result = resp.json()
    # spec-required response fields
    assert result["source_document_id"] == doc["id"]
    assert result["copied_tag_count"] == 1
    assert result["skipped_deprecated_count"] == 1     # C-2 deprecated
    assert result["skipped_resolved_comment_count"] == 1  # the resolved review
    assert len(result["clause_mappings"]) == 1
    m = result["clause_mappings"][0]
    assert m["clause_no"] == "C-1"
    assert m["source_clause_id"] == active["id"]
    assert [t["tag_name"] for t in m["inherited_tags"]] == ["AML"]
    target_id = result["target_document_id"]

    # target has one clause, carrying the tag, with no reviews
    rows = client.get(f"/api/v1/documents/{target_id}/clauses").json()
    assert len(rows) == 1
    assert rows[0]["clause"]["clause_no"] == "C-1"
    assert rows[0]["latest_review"] is None

    dash = client.get(f"/api/v1/documents/{target_id}/dashboard").json()
    assert dash["total_reviews"] == 0


def test_copy_detail_shows_origin_and_inherited_tags(client):
    doc = _make_document(client)
    c1 = _add_clause(client, doc["id"], clause_no="C-1")
    dep = _add_clause(client, doc["id"], clause_no="C-2")
    t1 = client.post("/api/v1/risk-tags", json={"name": "PII"}).json()
    t2 = client.post("/api/v1/risk-tags", json={"name": "SOX"}).json()
    client.post(f"/api/v1/clauses/{c1['id']}/tags", json={"tag_id": t1["id"]})
    client.post(f"/api/v1/clauses/{c1['id']}/tags", json={"tag_id": t2["id"]})
    # an unresolved and a resolved review on the source clause
    _add_review(client, c1["id"])
    r = _add_review(client, c1["id"])
    client.patch(f"/api/v1/reviews/{r['id']}/status",
                json={"to_status": "accepted", "operator": "A"})
    client.patch(f"/api/v1/reviews/{r['id']}/status",
                json={"to_status": "resolved", "operator": "A"})
    client.post(f"/api/v1/clauses/{dep['id']}/deprecate")

    target_id = client.post(f"/api/v1/documents/{doc['id']}/copies",
                           json={"version_no": "v2"}).json()["target_document_id"]

    detail = client.get(f"/api/v1/documents/{target_id}/copy-detail").json()
    assert detail["source_document_id"] == doc["id"]
    assert detail["target_document_id"] == target_id
    assert detail["skipped_deprecated_count"] == 1
    assert detail["skipped_resolved_comment_count"] == 1
    assert len(detail["clauses"]) == 1  # only the active clause carried over
    entry = detail["clauses"][0]
    assert entry["source_clause_no"] == "C-1"
    assert entry["target_clause_no"] == "C-1"
    assert entry["source_clause_id"] == c1["id"]
    # both risk tags inherited (risk classification, not comment status)
    assert sorted(t["tag_name"] for t in entry["inherited_tags"]) == ["PII", "SOX"]
    # summary explains that the 2 source reviews were not copied
    assert entry["not_copied_summary"]
    assert "2 review" in entry["not_copied_summary"][0]


def test_copy_detail_requires_copied_document(client):
    doc = _make_document(client)  # never used as a copy target
    resp = client.get(f"/api/v1/documents/{doc['id']}/copy-detail")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


def test_copy_mappings_query(client):
    doc = _make_document(client)
    _add_clause(client, doc["id"])
    client.post(f"/api/v1/documents/{doc['id']}/copies",
               json={"version_no": "v2"})
    client.post(f"/api/v1/documents/{doc['id']}/copies",
               json={"version_no": "v3"})
    mappings = client.get(f"/api/v1/documents/{doc['id']}/copies").json()
    assert len(mappings) == 2
    assert all(m["source_document_id"] == doc["id"] for m in mappings)
    # copy summary counters are persisted on each mapping
    assert all("copied_tag_count" in m for m in mappings)


# ---------------------------------------------------------------------------
# Risk board
# ---------------------------------------------------------------------------
def test_risk_board_counting_and_tag_gaps(client):
    doc = _make_document(client)
    c1 = _add_clause(client, doc["id"], clause_no="C-1")
    c2 = _add_clause(client, doc["id"], clause_no="C-2")
    c3 = _add_clause(client, doc["id"], clause_no="C-3")
    tag = client.post("/api/v1/risk-tags", json={"name": "PII"}).json()
    client.post(f"/api/v1/clauses/{c1['id']}/tags", json={"tag_id": tag["id"]})

    # C-1: one open critical (tagged)
    _add_review(client, c1["id"], risk_level="critical")
    # C-2: one high, resolved -> must count as resolved, NOT unprocessed (untagged)
    r2 = _add_review(client, c2["id"], risk_level="high")
    client.patch(f"/api/v1/reviews/{r2['id']}/status",
                json={"to_status": "accepted", "operator": "A"})
    client.patch(f"/api/v1/reviews/{r2['id']}/status",
                json={"to_status": "resolved", "operator": "A"})
    # C-3: one open low (untagged, not high risk)
    _add_review(client, c3["id"], risk_level="low")

    board = client.get(f"/api/v1/documents/{doc['id']}/risk-board").json()
    assert board["considered_clauses"] == 3
    assert board["tagged_clause_count"] == 1

    by_level = {b["risk_level"]: b for b in board["risk_breakdown"]}
    assert by_level["critical"]["unprocessed_count"] == 1
    assert by_level["critical"]["resolved_count"] == 0
    assert by_level["high"]["unprocessed_count"] == 0     # resolved excluded
    assert by_level["high"]["resolved_count"] == 1
    assert by_level["low"]["unprocessed_count"] == 1

    # top-risk list ordered highest first
    top = board["top_risk_clauses"]
    assert top[0]["clause_no"] == "C-1"
    assert top[0]["highest_risk_level"] == "critical"

    # untagged high-risk clauses: C-2 is high but untagged; C-1 tagged, C-3 low
    untagged = {c["clause_no"] for c in board["untagged_high_risk_clauses"]}
    assert untagged == {"C-2"}


def test_risk_board_excludes_deprecated_unless_requested(client):
    doc = _make_document(client)
    active = _add_clause(client, doc["id"], clause_no="C-1")
    dep = _add_clause(client, doc["id"], clause_no="C-2")
    _add_review(client, active["id"], risk_level="high")
    _add_review(client, dep["id"], risk_level="critical")
    client.post(f"/api/v1/clauses/{dep['id']}/deprecate")

    # default: deprecated clause excluded
    board = client.get(f"/api/v1/documents/{doc['id']}/risk-board").json()
    assert board["include_deprecated"] is False
    assert board["considered_clauses"] == 1
    nos = {c["clause_no"] for c in board["top_risk_clauses"]}
    assert nos == {"C-1"}
    by_level = {b["risk_level"]: b for b in board["risk_breakdown"]}
    assert by_level["critical"]["unprocessed_count"] == 0  # deprecated dropped

    # explicit include: deprecated clause participates
    board2 = client.get(
        f"/api/v1/documents/{doc['id']}/risk-board?include_deprecated=true"
    ).json()
    assert board2["include_deprecated"] is True
    assert board2["considered_clauses"] == 2
    by_level2 = {b["risk_level"]: b for b in board2["risk_breakdown"]}
    assert by_level2["critical"]["unprocessed_count"] == 1


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------
def test_missing_document_returns_not_found(client):
    resp = client.get("/api/v1/documents/9999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


def test_duplicate_risk_tag_name_conflict(client):
    client.post("/api/v1/risk-tags", json={"name": "Dup"})
    resp = client.post("/api/v1/risk-tags", json={"name": "Dup"})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "conflict"


# ---------------------------------------------------------------------------
# Consistency self-check
# ---------------------------------------------------------------------------
import os
import sqlite3


def _raw_conn():
    """Open the test's SQLite file directly to inject/inspect anomalies."""
    conn = sqlite3.connect(os.environ["CLAUSE_LEDGER_DB"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed_full_flow(client):
    """Exercise the documented end-to-end flow and return key ids."""
    doc = _make_document(client)
    # import clauses idempotently
    imp = client.post(f"/api/v1/documents/{doc['id']}/clauses/import", json={
        "mode": "skip_existing",
        "clauses": [
            {"clause_no": "C-1", "clause_text": "indemnify", "clause_type": "obligation",
             "importance": "high"},
            {"clause_no": "C-2", "clause_text": "termination", "clause_type": "right",
             "importance": "normal"},
        ],
    }).json()
    c1_id = next(m["final_clause_id"] for m in imp["mapping"] if m["clause_no"] == "C-1")
    tag = client.post("/api/v1/risk-tags", json={"name": "PII"}).json()
    client.post(f"/api/v1/clauses/{c1_id}/tags", json={"tag_id": tag["id"]})
    review = _add_review(client, c1_id, risk_level="high")
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "accepted", "operator": "Alice"})
    client.patch(f"/api/v1/reviews/{review['id']}/status",
                json={"to_status": "resolved", "operator": "Alice"})
    return doc, c1_id, review, tag


def test_consistency_check_passes_on_healthy_ledger(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # also copy a version to populate copy mappings
    client.post(f"/api/v1/documents/{doc['id']}/copies", json={"version_no": "v2"})

    resp = client.get("/api/v1/consistency-check")
    assert resp.status_code == 200
    report = resp.json()
    assert report["healthy"] is True
    assert report["total_problems"] == 0
    assert "T" in report["generated_at"]  # ISO 8601
    # all seven-plus checks present and passing
    names = {c["name"] for c in report["checks"]}
    assert {
        "reviews_added_after_deprecation",
        "tags_bound_after_deprecation",
        "resolved_reviews_without_process_record",
        "duplicate_tag_bindings",
        "missing_copy_mappings",
        "dashboard_detail_mismatch",
        "duplicate_clause_no",
        "non_open_reviews_in_unprocessed",
    }.issubset(names)
    assert all(c["passed"] and c["problem_count"] == 0 for c in report["checks"])


def test_consistency_check_detects_review_after_deprecation(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # deprecate through the API (records deprecated_at = now), then inject a
    # review dated in the future so it is unambiguously after deprecation
    assert client.post(f"/api/v1/clauses/{c1_id}/deprecate").status_code == 200
    conn = _raw_conn()
    conn.execute(
        """INSERT INTO reviews
           (clause_id, reviewer_name, comment_text, risk_level, process_status, created_at)
           VALUES (?, 'Sneaky', 'late', 'high', 'open', ?)""",
        (c1_id, "2099-06-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    report = client.get("/api/v1/consistency-check").json()
    assert report["healthy"] is False
    check = next(c for c in report["checks"]
                 if c["name"] == "reviews_added_after_deprecation")
    assert check["passed"] is False
    assert check["problem_count"] == 1
    assert check["details"][0]["clause_id"] == c1_id


def test_consistency_check_detects_resolved_without_record(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # inject a resolved review with no process record backing it
    conn = _raw_conn()
    conn.execute(
        """INSERT INTO reviews
           (clause_id, reviewer_name, comment_text, risk_level, process_status, created_at)
           VALUES (?, 'X', 'done', 'low', 'resolved', ?)""",
        (c1_id, "2026-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    report = client.get("/api/v1/consistency-check").json()
    assert report["healthy"] is False
    check = next(c for c in report["checks"]
                 if c["name"] == "resolved_reviews_without_process_record")
    assert check["problem_count"] == 1


def test_consistency_check_detects_duplicate_tag_binding(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # UNIQUE(clause_id, tag_id) blocks duplicates via API and direct INSERT, so
    # rebuild clause_tags without the constraint to simulate corruption.
    conn = _raw_conn()
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE clause_tags RENAME TO clause_tags_old;
        CREATE TABLE clause_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clause_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO clause_tags SELECT * FROM clause_tags_old;
        DROP TABLE clause_tags_old;
        """
    )
    conn.execute(
        "INSERT INTO clause_tags (clause_id, tag_id, created_at) VALUES (?, ?, ?)",
        (c1_id, tag["id"], "2026-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    report = client.get("/api/v1/consistency-check").json()
    check = next(c for c in report["checks"] if c["name"] == "duplicate_tag_bindings")
    assert check["passed"] is False
    assert check["details"][0]["clause_id"] == c1_id


def test_consistency_check_detects_duplicate_clause_no(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # The UNIQUE(document_id, clause_no) guard makes duplicates impossible via
    # the API and even via direct INSERT. To simulate a corrupted ledger the
    # self-check must catch, rebuild the clauses table without that constraint
    # and then insert a colliding row.
    conn = _raw_conn()
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        ALTER TABLE clauses RENAME TO clauses_old;
        CREATE TABLE clauses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            clause_no TEXT NOT NULL,
            clause_text TEXT NOT NULL,
            clause_type TEXT NOT NULL,
            importance TEXT NOT NULL,
            deprecated INTEGER NOT NULL DEFAULT 0,
            deprecated_at TEXT
        );
        INSERT INTO clauses SELECT * FROM clauses_old;
        DROP TABLE clauses_old;
        """
    )
    conn.execute(
        """INSERT INTO clauses (document_id, clause_no, clause_text,
                                clause_type, importance, deprecated)
           VALUES (?, 'C-1', 'dup', 'other', 'low', 0)""",
        (doc["id"],))
    conn.commit()
    conn.close()

    report = client.get("/api/v1/consistency-check").json()
    check = next(c for c in report["checks"] if c["name"] == "duplicate_clause_no")
    assert check["passed"] is False
    assert check["details"][0]["clause_no"] == "C-1"


def test_consistency_check_detects_non_open_in_unprocessed(client):
    doc, c1_id, review, tag = _seed_full_flow(client)
    # inject a review with a corrupted status that the unprocessed filter
    # cannot classify correctly
    conn = _raw_conn()
    conn.execute(
        """INSERT INTO reviews
           (clause_id, reviewer_name, comment_text, risk_level, process_status, created_at)
           VALUES (?, 'Y', 'weird', 'high', 'REJECTED', ?)""",
        (c1_id, "2026-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    report = client.get("/api/v1/consistency-check").json()
    check = next(c for c in report["checks"]
                 if c["name"] == "non_open_reviews_in_unprocessed")
    assert check["passed"] is False
    assert check["problem_count"] == 1


# ---------------------------------------------------------------------------
# README documented flow is executable, and every route keeps /api/v1
# ---------------------------------------------------------------------------
def test_readme_end_to_end_flow_is_executable(client):
    # 1. create document
    doc = _make_document(client, title="Vendor MSA", version_no="v1")
    # 2. import clauses (idempotent)
    imp = client.post(f"/api/v1/documents/{doc['id']}/clauses/import", json={
        "mode": "update_existing",
        "clauses": [
            {"clause_no": "C-1", "clause_text": "indemnify", "clause_type": "obligation",
             "importance": "high"},
        ],
    })
    assert imp.status_code == 200
    c1_id = imp.json()["mapping"][0]["final_clause_id"]
    # 3. add review
    review = _add_review(client, c1_id, risk_level="critical")
    # 4. create + bind tag
    tag = client.post("/api/v1/risk-tags", json={"name": "AML"}).json()
    bind = client.post(f"/api/v1/clauses/{c1_id}/tags", json={"tag_id": tag["id"]})
    assert bind.status_code == 201
    # 5. process the opinion open -> accepted -> resolved
    assert client.patch(f"/api/v1/reviews/{review['id']}/status",
                        json={"to_status": "accepted", "operator": "A"}).status_code == 200
    assert client.patch(f"/api/v1/reviews/{review['id']}/status",
                        json={"to_status": "resolved", "operator": "A"}).status_code == 200
    # 6. copy to a new version
    copy = client.post(f"/api/v1/documents/{doc['id']}/copies",
                      json={"version_no": "v2"})
    assert copy.status_code == 201
    target_id = copy.json()["target_document_id"]
    # risk board + copy detail + self-check all succeed on the resulting ledger
    assert client.get(f"/api/v1/documents/{doc['id']}/risk-board").status_code == 200
    assert client.get(f"/api/v1/documents/{target_id}/copy-detail").status_code == 200
    report = client.get("/api/v1/consistency-check").json()
    assert report["healthy"] is True


def test_all_routes_use_api_v1_prefix(client):
    from app.main import app
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            # only /health and framework routes (docs/openapi) may sit outside
            assert path in {
                "/health", "/", "/openapi.json", "/docs", "/docs/oauth2-redirect",
                "/redoc",
            }, f"unexpected non-prefixed route: {path}"
        else:
            assert path.startswith("/api/v1"), f"bad prefix: {path}"

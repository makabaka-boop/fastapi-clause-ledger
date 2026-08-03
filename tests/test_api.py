"""端到端 API 测试，覆盖全部业务规则。"""


def _create_doc(client, title="制度A", version="v1"):
    return client.post(
        "/api/v1/documents",
        json={"title": title, "source_department": "合规部", "version_no": version},
    ).json()


def _batch(client, doc_id, clauses):
    return client.post(f"/api/v1/documents/{doc_id}/clauses/batch", json={"clauses": clauses})


def _review(client, clause_id, risk="high"):
    return client.post(
        f"/api/v1/clauses/{clause_id}/reviews",
        json={"reviewer_name": "张三", "comment_text": "存在风险", "risk_level": risk},
    )


# ---------- 健康检查 ----------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------- 文档 ----------

def test_create_document(client):
    resp = client.post(
        "/api/v1/documents",
        json={"title": "合同管理办法", "source_department": "法务部", "version_no": "v1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["document_status"] == "draft"
    assert "created_at" in body


def test_update_document_status(client, document):
    resp = client.patch(
        f"/api/v1/documents/{document['id']}/status", json={"document_status": "in_review"}
    )
    assert resp.status_code == 200
    assert resp.json()["document_status"] == "in_review"

    resp = client.patch(
        f"/api/v1/documents/{document['id']}/status", json={"document_status": "bogus"}
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


def test_document_not_found(client):
    resp = client.patch("/api/v1/documents/999/status", json={"document_status": "approved"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "not_found"
    assert set(body.keys()) == {"error_code", "message", "details"}


# ---------- 条款 ----------

def test_duplicate_clause_no_rejected(client, document):
    payload = {"clauses": [{"clause_no": "1.1", "clause_text": "条款一"}]}
    assert _batch(client, document["id"], payload["clauses"]).status_code == 201
    resp = _batch(client, document["id"], payload["clauses"])
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "duplicate_clause_no"


def test_same_clause_no_allowed_across_documents(client):
    doc1 = _create_doc(client, "A", "v1")
    doc2 = _create_doc(client, "B", "v1")
    assert _batch(client, doc1["id"], [{"clause_no": "1.1", "clause_text": "x"}]).status_code == 201
    assert _batch(client, doc2["id"], [{"clause_no": "1.1", "clause_text": "y"}]).status_code == 201


def test_import_skip_existing(client, document):
    doc_id = document["id"]
    _batch(client, doc_id, [{"clause_no": "1.1", "clause_text": "旧文本"}])
    resp = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "skip_existing",
            "clauses": [
                {"clause_no": "1.1", "clause_text": "新文本"},
                {"clause_no": "1.2", "clause_text": "全新条款"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1

    # 旧条款 ID 与最终条款 ID 的映射
    mapping = {m["action"]: m for m in body["clause_id_mapping"]}
    assert mapping["skipped"]["old_clause_id"] == body["skipped"][0]["id"]
    assert mapping["skipped"]["final_clause_id"] == body["skipped"][0]["id"]
    assert mapping["created"]["old_clause_id"] is None
    assert mapping["created"]["final_clause_id"] == body["created"][0]["id"]

    clauses = client.get(f"/api/v1/documents/{doc_id}/clauses").json()
    by_no = {c["clause"]["clause_no"]: c["clause"] for c in clauses}
    assert by_no["1.1"]["clause_text"] == "旧文本"  # 未被覆盖

    # 幂等：重复导入结果一致
    resp2 = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={"mode": "skip_existing", "clauses": [{"clause_no": "1.2", "clause_text": "x"}]},
    )
    assert resp2.json()["skipped_count"] == 1
    assert resp2.json()["created_count"] == 0


def test_import_update_existing(client, document):
    doc_id = document["id"]
    _batch(client, doc_id, [{"clause_no": "1.1", "clause_text": "旧文本"}])
    resp = client.post(
        f"/api/v1/documents/{doc_id}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {"clause_no": "1.1", "clause_text": "新文本"},
                {"clause_no": "1.2", "clause_text": "新增条款"},
            ],
        },
    )
    body = resp.json()
    assert body["updated_count"] == 1
    assert body["created_count"] == 1
    # 更新时旧 ID 即最终 ID
    mapping = {m["action"]: m for m in body["clause_id_mapping"]}
    assert mapping["updated"]["old_clause_id"] == mapping["updated"]["final_clause_id"]
    clauses = client.get(f"/api/v1/documents/{doc_id}/clauses").json()
    by_no = {c["clause"]["clause_no"]: c["clause"] for c in clauses}
    assert by_no["1.1"]["clause_text"] == "新文本"


def test_import_invalid_mode(client, document):
    resp = client.post(
        f"/api/v1/documents/{document['id']}/clauses/import",
        json={"mode": "overwrite", "clauses": []},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


# ---------- 废弃条款约束 ----------

def test_deprecated_clause_rejects_review_and_binding(client, clause):
    client.post(f"/api/v1/clauses/{clause['id']}/deprecate")

    resp = _review(client, clause["id"])
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "clause_deprecated"

    tag = client.post("/api/v1/tags", json={"tag_name": "财务风险"}).json()
    resp = client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "clause_deprecated"


def test_deprecated_clause_rejects_status_change_and_record(client, clause):
    """废弃条款后，未处理意见的状态变更与处理记录写入都被拒绝。"""
    review = _review(client, clause["id"]).json()
    client.post(f"/api/v1/clauses/{clause['id']}/deprecate")

    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "clause_deprecated"

    resp = client.post(
        f"/api/v1/reviews/{review['id']}/records",
        json={"to_status": "accepted", "operator_name": "李四"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "clause_deprecated"


def test_deprecated_clause_history_still_queryable(client, document, clause):
    """废弃后历史意见和历史标签仍可查询。"""
    review = _review(client, clause["id"], risk="high").json()
    tag = client.post("/api/v1/tags", json={"tag_name": "历史标签"}).json()
    client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]})
    client.post(f"/api/v1/clauses/{clause['id']}/deprecate")

    # 历史意见可查
    reviews = client.get(f"/api/v1/clauses/{clause['id']}/reviews").json()
    assert len(reviews) == 1
    assert reviews[0]["id"] == review["id"]
    assert reviews[0]["risk_level"] == "high"

    # 历史标签可查（随文档条款返回）
    clauses = client.get(f"/api/v1/documents/{document['id']}/clauses").json()
    target = [c for c in clauses if c["clause"]["id"] == clause["id"]][0]
    assert target["clause"]["deprecated"] is True
    assert len(target["tags"]) == 1
    assert target["tags"][0]["tag_name"] == "历史标签"
    assert target["latest_review"]["id"] == review["id"]


# ---------- 审阅意见与状态机 ----------

def test_review_risk_level_validation(client, clause):
    resp = client.post(
        f"/api/v1/clauses/{clause['id']}/reviews",
        json={"reviewer_name": "张三", "comment_text": "x", "risk_level": "extreme"},
    )
    assert resp.status_code == 422


def test_status_flow_writes_records(client, clause):
    review = _review(client, clause["id"]).json()
    assert review["process_status"] == "open"

    # open -> accepted
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四", "note": "认可该风险"},
    )
    assert resp.status_code == 200
    assert resp.json()["process_status"] == "accepted"

    # accepted -> resolved
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "resolved", "operator_name": "李四"},
    )
    assert resp.json()["process_status"] == "resolved"

    # 处理历史包含两条记录
    history = client.get(f"/api/v1/reviews/{review['id']}/records").json()
    assert len(history) == 2
    assert history[0]["from_status"] == "open" and history[0]["to_status"] == "accepted"
    assert history[1]["from_status"] == "accepted" and history[1]["to_status"] == "resolved"

    # 禁止从 resolved 回退
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "open", "operator_name": "李四"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_status_transition"


def test_invalid_transition_open_to_resolved(client, clause):
    review = _review(client, clause["id"]).json()
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "resolved", "operator_name": "王五"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_status_transition"


def test_rejected_cannot_return_to_open(client, clause):
    """rejected 为终态，不能回到 open。"""
    review = _review(client, clause["id"]).json()
    client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "rejected", "operator_name": "王五"},
    )
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "open", "operator_name": "王五"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_status_transition"
    assert resp.json()["details"]["from_status"] == "rejected"
    assert resp.json()["details"]["to_status"] == "open"

    # 写处理记录方式同样被拒绝
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/records",
        json={"to_status": "open", "operator_name": "王五"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "invalid_status_transition"


def test_process_record_integrity(client, clause):
    """处理记录完整记录 from/to/操作人/备注，且与意见状态同步。"""
    review = _review(client, clause["id"]).json()
    client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四", "note": "确认风险"},
    )
    client.post(
        f"/api/v1/reviews/{review['id']}/records",
        json={"to_status": "resolved", "operator_name": "赵六", "note": "已整改"},
    )

    history = client.get(f"/api/v1/reviews/{review['id']}/records").json()
    assert len(history) == 2
    first, second = history
    assert (first["from_status"], first["to_status"]) == ("open", "accepted")
    assert first["operator_name"] == "李四" and first["note"] == "确认风险"
    assert (second["from_status"], second["to_status"]) == ("accepted", "resolved")
    assert second["operator_name"] == "赵六" and second["note"] == "已整改"
    for rec in history:
        assert rec["review_id"] == review["id"]
        assert "created_at" in rec

    # 意见最终状态与最后一条记录一致
    reviews = client.get(f"/api/v1/clauses/{clause['id']}/reviews").json()
    assert reviews[0]["process_status"] == "resolved"


def test_write_process_record_endpoint(client, clause):
    review = _review(client, clause["id"]).json()
    resp = client.post(
        f"/api/v1/reviews/{review['id']}/records",
        json={"to_status": "rejected", "operator_name": "王五", "note": "误报"},
    )
    assert resp.status_code == 201
    assert resp.json()["to_status"] == "rejected"


# ---------- 标签 ----------

def test_duplicate_binding_rejected(client, clause):
    tag = client.post("/api/v1/tags", json={"tag_name": "合同风险"}).json()
    assert client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]}).status_code == 201
    resp = client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]})
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "duplicate_tag_binding"


def test_open_reviews_by_risk_level(client, document, clause):
    _review(client, clause["id"], risk="high")
    r2 = _review(client, clause["id"], risk="high").json()
    _review(client, clause["id"], risk="low")
    # 将其中一条 high 置为 accepted，不再属于 open
    client.post(
        f"/api/v1/reviews/{r2['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四"},
    )
    resp = client.get("/api/v1/reviews", params={"risk_level": "high"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["risk_level"] == "high"


def test_tag_risk_distribution(client, clause):
    tag = client.post("/api/v1/tags", json={"tag_name": "操作风险"}).json()
    client.post(f"/api/v1/clauses/{clause['id']}/tags", json={"tag_id": tag["id"]})
    _review(client, clause["id"], risk="medium")
    _review(client, clause["id"], risk="medium")
    _review(client, clause["id"], risk="critical")

    dist = client.get(f"/api/v1/tags/{tag['id']}/risk_distribution").json()
    by_level = {d["risk_level"]: d for d in dist}
    assert by_level["medium"]["total_count"] == 2
    assert by_level["medium"]["open_count"] == 2
    assert by_level["critical"]["total_count"] == 1
    assert by_level["low"]["total_count"] == 0


# ---------- 文档条款与最新意见 ----------

def test_document_clauses_with_latest_review(client, document, clause):
    _review(client, clause["id"], risk="low")
    import time

    time.sleep(0.01)
    _review(client, clause["id"], risk="high")
    clauses = client.get(f"/api/v1/documents/{document['id']}/clauses").json()
    assert len(clauses) == 1
    assert clauses[0]["latest_review"]["risk_level"] == "high"


# ---------- 复制文档版本 ----------

def test_copy_document_skips_deprecated_and_resolved(client, document):
    doc_id = document["id"]
    clauses = _batch(
        client,
        doc_id,
        [
            {"clause_no": "1.1", "clause_text": "有效条款"},
            {"clause_no": "1.2", "clause_text": "废弃条款"},
        ],
    ).json()
    active, deprecated = clauses[0], clauses[1]
    client.post(f"/api/v1/clauses/{deprecated['id']}/deprecate")

    tag = client.post("/api/v1/tags", json={"tag_name": "法律风险"}).json()
    client.post(f"/api/v1/clauses/{active['id']}/tags", json={"tag_id": tag["id"]})

    # 一条 open 意见 + 一条 resolved 意见
    _review(client, active["id"], risk="high")
    r2 = _review(client, active["id"], risk="medium").json()
    client.post(
        f"/api/v1/reviews/{r2['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四"},
    )
    client.post(
        f"/api/v1/reviews/{r2['id']}/status",
        json={"to_status": "resolved", "operator_name": "李四"},
    )

    resp = client.post(f"/api/v1/documents/{doc_id}/copy", json={"version_no": "v2"})
    assert resp.status_code == 201
    mapping = resp.json()
    assert mapping["source_document_id"] == doc_id
    assert mapping["copied_clause_count"] == 1
    assert mapping["skipped_deprecated_count"] == 1
    assert mapping["copied_review_count"] == 1  # resolved 未复制
    assert mapping["skipped_resolved_comment_count"] == 1
    assert mapping["copied_tag_count"] == 1
    # clause_mappings 反映新旧条款对应及继承标签
    assert len(mapping["clause_mappings"]) == 1
    cm = mapping["clause_mappings"][0]
    assert cm["source_clause_id"] == active["id"]
    assert cm["source_clause_no"] == "1.1"
    assert cm["inherited_tag_ids"] == [tag["id"]]

    target_clauses = client.get(
        f"/api/v1/documents/{mapping['target_document_id']}/clauses"
    ).json()
    assert len(target_clauses) == 1
    assert target_clauses[0]["clause"]["clause_no"] == "1.1"
    assert target_clauses[0]["latest_review"]["risk_level"] == "high"
    assert len(target_clauses[0]["tags"]) == 1

    # 查询复制映射
    mappings = client.get("/api/v1/copies", params={"document_id": doc_id}).json()
    assert len(mappings) == 1
    assert mappings[0]["source_document_id"] == doc_id


def test_copy_details_by_target_document(client, document):
    """复制详情：按目标文档查看原条款、继承标签与未复制原因。"""
    doc_id = document["id"]
    clauses = _batch(
        client,
        doc_id,
        [
            {"clause_no": "1.1", "clause_text": "有效条款"},
            {"clause_no": "1.2", "clause_text": "废弃条款"},
        ],
    ).json()
    active, deprecated = clauses[0], clauses[1]
    client.post(f"/api/v1/clauses/{deprecated['id']}/deprecate")

    tag = client.post("/api/v1/tags", json={"tag_name": "合同风险"}).json()
    client.post(f"/api/v1/clauses/{active['id']}/tags", json={"tag_id": tag["id"]})

    r = _review(client, active["id"], risk="medium").json()
    client.post(f"/api/v1/reviews/{r['id']}/status", json={"to_status": "accepted", "operator_name": "李四"})
    client.post(f"/api/v1/reviews/{r['id']}/status", json={"to_status": "resolved", "operator_name": "李四"})

    mapping = client.post(f"/api/v1/documents/{doc_id}/copy", json={"version_no": "v2"}).json()
    target_id = mapping["target_document_id"]

    resp = client.get(f"/api/v1/documents/{target_id}/copy_details")
    assert resp.status_code == 200
    details = resp.json()
    assert details["source_document_id"] == doc_id
    assert details["target_document_id"] == target_id

    # 新条款 -> 原条款 + 继承标签
    assert len(details["clauses"]) == 1
    detail = details["clauses"][0]
    assert detail["source_clause_id"] == active["id"]
    assert detail["source_clause_no"] == "1.1"
    assert [t["tag_name"] for t in detail["inherited_tags"]] == ["合同风险"]
    # 该条款下 resolved 意见未复制，带原因
    assert len(detail["skipped_items"]) == 1
    skipped = detail["skipped_items"][0]
    assert skipped["item_type"] == "review"
    assert skipped["reason"] == "resolved_review"
    assert skipped["source_review_id"] == r["id"]

    # 废弃条款在文档级未复制清单中
    assert len(details["skipped_clauses"]) == 1
    assert details["skipped_clauses"][0]["source_clause_id"] == deprecated["id"]
    assert details["skipped_clauses"][0]["reason"] == "deprecated_clause"


def test_copy_details_not_a_copy_target(client, document):
    resp = client.get(f"/api/v1/documents/{document['id']}/copy_details")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


# ---------- 风险看板 ----------

def test_risk_dashboard(client, document, clause):
    _review(client, clause["id"], risk="high")
    _review(client, clause["id"], risk="low")
    dash = client.get(f"/api/v1/documents/{document['id']}/risk_dashboard").json()
    assert dash["clause_count"] == 1
    assert dash["review_count"] == 2
    assert dash["open_review_count"] == 2
    assert dash["risk_distribution"]["high"] == 1
    assert dash["risk_distribution"]["low"] == 1
    assert dash["status_distribution"]["open"] == 2


def test_dashboard_statistics(client, document):
    """看板口径：open/resolved 分布、最高风险条款、标签统计、废弃条款默认排除。"""
    doc_id = document["id"]
    c1, c2, c3 = _batch(
        client,
        doc_id,
        [
            {"clause_no": "1.1", "clause_text": "条款一"},
            {"clause_no": "1.2", "clause_text": "条款二"},
            {"clause_no": "1.3", "clause_text": "条款三（将废弃）"},
        ],
    ).json()

    # c1: 一条 high open + 一条 critical resolved；带标签
    r1 = _review(client, c1["id"], risk="high").json()
    r2 = _review(client, c1["id"], risk="critical").json()
    client.post(f"/api/v1/reviews/{r2['id']}/status", json={"to_status": "accepted", "operator_name": "李四"})
    client.post(f"/api/v1/reviews/{r2['id']}/status", json={"to_status": "resolved", "operator_name": "李四"})
    tag = client.post("/api/v1/tags", json={"tag_name": "重大风险"}).json()
    client.post(f"/api/v1/clauses/{c1['id']}/tags", json={"tag_id": tag["id"]})

    # c2: 一条 medium open；无标签
    _review(client, c2["id"], risk="medium")

    # c3: 废弃 + 一条 critical open（默认不应计入看板）
    _review(client, c3["id"], risk="critical")
    client.post(f"/api/v1/clauses/{c3['id']}/deprecate")

    dash = client.get(f"/api/v1/documents/{doc_id}/risk_dashboard").json()
    assert dash["include_deprecated"] is False
    # resolved 不出现在未处理统计
    assert dash["open_risk_distribution"] == {"low": 0, "medium": 1, "high": 1, "critical": 0}
    assert dash["resolved_risk_distribution"]["critical"] == 1
    assert dash["open_review_count"] == 2
    # 最高风险条款：c1（critical 来自其意见最高等级）
    assert dash["highest_risk_level"] == "critical"
    assert [c["clause_id"] for c in dash["highest_risk_clauses"]] == [c1["id"]]
    # 标签统计
    assert dash["tagged_clause_count"] == 1
    # 无标签高风险：c1 有标签、c2 只是 medium，应为空
    assert dash["untagged_high_risk_clauses"] == []
    # 废弃条款默认不参与
    assert dash["clause_count"] == 2
    assert dash["deprecated_clause_count"] == 1

    # 显式包含废弃条款后，c3 的 critical open 计入
    dash_inc = client.get(
        f"/api/v1/documents/{doc_id}/risk_dashboard", params={"include_deprecated": True}
    ).json()
    assert dash_inc["include_deprecated"] is True
    assert dash_inc["clause_count"] == 3
    assert dash_inc["open_risk_distribution"]["critical"] == 1
    assert dash_inc["open_review_count"] == 3
    highest_ids = {c["clause_id"] for c in dash_inc["highest_risk_clauses"]}
    assert highest_ids == {c1["id"], c3["id"]}
    # c3 无标签且为高风险 -> 出现在无标签高风险列表
    untagged_ids = {c["clause_id"] for c in dash_inc["untagged_high_risk_clauses"]}
    assert untagged_ids == {c3["id"]}

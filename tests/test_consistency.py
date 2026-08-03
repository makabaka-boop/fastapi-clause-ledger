"""一致性自检接口与 README 流程可执行性测试。"""

from app.database import SessionLocal
from app.models import Review


def _checks_by_name(body):
    return {c["check_name"]: c for c in body["checks"]}


def _full_flow(client):
    """README 完整操作流程：创建文档 -> 导入条款 -> 添加意见 ->
    绑定标签 -> 处理意见 -> 复制新版本 -> 看板。返回关键 ID。"""
    # 1. 创建文档
    doc = client.post(
        "/api/v1/documents",
        json={"title": "供应商管理制度", "source_department": "合规部", "version_no": "v1"},
    ).json()

    # 2. 批量新增 + 幂等导入条款
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "供应商准入须审批"}]},
    )
    client.post(
        f"/api/v1/documents/{doc['id']}/clauses/import",
        json={
            "mode": "update_existing",
            "clauses": [
                {"clause_no": "1.1", "clause_text": "供应商准入须两级审批"},
                {"clause_no": "1.2", "clause_text": "年度复审"},
            ],
        },
    )

    clauses = client.get(f"/api/v1/documents/{doc['id']}/clauses").json()
    clause_id = clauses[0]["clause"]["id"]

    # 3. 添加审阅意见
    review = client.post(
        f"/api/v1/clauses/{clause_id}/reviews",
        json={"reviewer_name": "张三", "comment_text": "审批层级不足", "risk_level": "high"},
    ).json()

    # 4. 创建并绑定风险标签
    tag = client.post("/api/v1/tags", json={"tag_name": "流程风险"}).json()
    client.post(f"/api/v1/clauses/{clause_id}/tags", json={"tag_id": tag["id"]})

    # 5. 处理意见：open -> accepted -> resolved（每次自动写处理记录）
    client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "accepted", "operator_name": "李四", "note": "确认"},
    )
    client.post(
        f"/api/v1/reviews/{review['id']}/status",
        json={"to_status": "resolved", "operator_name": "李四", "note": "已修订"},
    )

    # 6. 复制新版本
    copy_result = client.post(
        f"/api/v1/documents/{doc['id']}/copy", json={"version_no": "v2"}
    ).json()

    # 7. 查看风险看板
    dash = client.get(f"/api/v1/documents/{doc['id']}/risk_dashboard").json()

    return {"doc": doc, "clause_id": clause_id, "review": review, "tag": tag,
            "copy": copy_result, "dashboard": dash}


def test_consistency_all_pass(client):
    _full_flow(client)
    resp = client.get("/api/v1/consistency/checks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_passed"] is True
    assert body["failed_count"] == 0
    assert body["check_count"] == 7
    assert "checked_at" in body
    for check in body["checks"]:
        assert check["passed"] is True
        assert check["issue_count"] == 0
        assert check["details"] == []


def test_consistency_detects_issues(client):
    """直接向数据库注入不一致数据后，自检应报告问题明细。"""
    flow = _full_flow(client)
    clause_id = flow["clause_id"]

    db = SessionLocal()
    try:
        # 违规 1：resolved 意见缺少处理记录
        bad_resolved = Review(
            clause_id=clause_id,
            reviewer_name="注入",
            comment_text="缺少处理记录",
            risk_level="low",
            process_status="resolved",
        )
        db.add(bad_resolved)
        # 违规 2：非法 process_status 取值
        bad_status = Review(
            clause_id=clause_id,
            reviewer_name="注入",
            comment_text="非法状态",
            risk_level="medium",
            process_status="pending",
        )
        db.add(bad_status)
        db.commit()

        # 违规 3：条款废弃后新增意见
        client.post(f"/api/v1/clauses/{clause_id}/deprecate")
        late_review = Review(
            clause_id=clause_id,
            reviewer_name="注入",
            comment_text="废弃后新增",
            risk_level="high",
            process_status="open",
        )
        db.add(late_review)
        db.commit()
        late_review_id = late_review.id
        bad_resolved_id = bad_resolved.id
        bad_status_id = bad_status.id
    finally:
        db.close()

    body = client.get("/api/v1/consistency/checks").json()
    assert body["overall_passed"] is False
    assert body["failed_count"] >= 3

    checks = _checks_by_name(body)
    deprecated_check = checks["deprecated_clause_operations"]
    assert deprecated_check["passed"] is False
    assert any(
        d["kind"] == "review_after_deprecation" and d["review_id"] == late_review_id
        for d in deprecated_check["details"]
    )

    resolved_check = checks["resolved_reviews_missing_process_record"]
    assert resolved_check["passed"] is False
    assert any(d["review_id"] == bad_resolved_id for d in resolved_check["details"])

    purity_check = checks["open_list_purity"]
    assert purity_check["passed"] is False
    assert any(d["review_id"] == bad_status_id for d in purity_check["details"])


def test_readme_flow_executable(client):
    """README 中的完整操作流程可按顺序执行成功。"""
    flow = _full_flow(client)
    assert flow["dashboard"]["review_count"] == 1
    assert flow["dashboard"]["resolved_risk_distribution"]["high"] == 1
    # 复制时 resolved 意见不复制，标签继承
    assert flow["copy"]["skipped_resolved_comment_count"] == 1
    assert flow["copy"]["copied_tag_count"] == 1
    # 流程结束后台账自洽
    body = client.get("/api/v1/consistency/checks").json()
    assert body["overall_passed"] is True


def test_new_endpoints_use_api_v1_prefix(client):
    """所有业务接口（含新增）都在 /api/v1 前缀下。"""
    assert client.get("/consistency/checks").status_code == 404

    openapi = client.get("/openapi.json").json()
    business_paths = [
        p for p in openapi["paths"]
        if p not in ("/health",) and not p.startswith("/docs") and not p.startswith("/redoc")
    ]
    assert business_paths, "应存在业务接口"
    for path in business_paths:
        assert path.startswith("/api/v1"), f"{path} 缺少 /api/v1 前缀"
    # 本轮新增接口确实出现在 /api/v1 下
    assert "/api/v1/consistency/checks" in openapi["paths"]
    assert "/api/v1/documents/{document_id}/copy_details" in openapi["paths"]

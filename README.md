# fastapi-clause-ledger

合规条款审阅台账服务，面向合规团队管理文档、条款、风险标签、审阅意见、处理记录、版本复制和风险看板。基于 FastAPI 分层架构、SQLite 持久化与 Pydantic 严格校验，重点关注审计一致性与状态机约束。

## 技术栈

- Python 3.9+
- FastAPI 0.115
- SQLAlchemy 2.0
- Pydantic 2
- SQLite
- pytest + httpx

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

服务监听 `0.0.0.0:18103`：

- 健康检查：`GET /health`
- 业务接口：统一前缀 `/api/v1`
- 交互式文档：`http://127.0.0.1:18103/docs`

可通过环境变量覆盖数据库连接：

```bash
export DATABASE_URL="sqlite:///./clause_ledger.db"
```

## 运行测试

```bash
pytest -q
```

测试使用内存 SQLite（`StaticPool`），每个用例独立建表销毁，不污染本地数据。

## 分层架构

```
main.py                  # 应用入口、lifespan、路由挂载
app/
├── config.py            # 配置（端口、前缀、数据库）
├── database.py          # 引擎、会话、Base、init_db
├── deps.py              # FastAPI 依赖（get_db）
├── enums.py             # RiskLevel / ProcessStatus / DocumentStatus / ImportMode
├── models.py            # SQLAlchemy ORM 模型
├── schemas.py           # Pydantic 请求/响应模型
├── repositories.py      # 仓储层：只做数据访问
├── services.py          # 服务层：业务规则与事务边界
├── state_machine.py     # 意见状态机与审计规则
├── consistency.py       # 台账一致性自检服务
├── exceptions.py        # 领域异常
├── error_handlers.py    # 全局异常处理（统一错误体）
└── routers/             # 路由层：参数校验、调用 service、序列化
    ├── documents.py
    ├── clauses.py
    ├── comments.py
    ├── tags.py
    ├── copies.py
    ├── dashboard.py
    ├── consistency.py
    ├── health.py
    └── api.py           # v1 路由聚合
tests/                   # pytest 用例
```

依赖方向：`router → service → repository → model`。状态机、异常、枚举被 service 复用，router 不直接访问仓储。

## 数据模型

| 表 | 关键字段 |
|---|---|
| `documents` | `title`、`source_department`、`version_no`、`document_status`、`created_at` |
| `clauses` | `document_id`、`clause_no`、`clause_text`、`clause_type`、`importance`、`deprecated`、`created_at` |
| `comments` | `clause_id`、`reviewer_name`、`comment_text`、`risk_level`、`process_status`、`created_at` |
| `risk_tags` | `name`(唯一)、`description`、`created_at` |
| `tag_bindings` | `clause_id`、`tag_id`、`created_at` |
| `processing_records` | `comment_id`、`from_status`、`to_status`、`action`、`operator`、`note`、`created_at` |
| `document_copies` | `source_document_id`、`target_document_id`、`copy_type`、`created_at` |

约束：

- `(documents.title, documents.version_no)` 唯一。
- `(clauses.document_id, clauses.clause_no)` 唯一，同一文档下 `clause_no` 不允许重复。
- `(tag_bindings.clause_id, tag_bindings.tag_id)` 唯一。

## 枚举与约定

- 风险等级 `risk_level`：`low`、`medium`、`high`、`critical`
- 处理状态 `process_status`：`open`、`accepted`、`rejected`、`resolved`
- 幂等导入 `mode`：`skip_existing`、`update_existing`
- 字段统一 `snake_case`，时间统一 ISO 8601（UTC，带 `Z`/时区偏移）。

错误响应固定结构：

```json
{ "error_code": "not_found", "message": "...", "details": { } }
```

## 状态机

定义在 `app/state_machine.py`：

```
open ──► accepted ──► resolved
open ──► rejected ──► resolved
accepted ──► rejected
```

- `open → accepted`、`open → rejected`、`accepted → resolved` 必须写处理记录。
- `resolved` 为终态，禁止任何回退。
- 非法迁移返回 `409 invalid_state_transition`。

## 接口清单

### 文档
- `POST   /api/v1/documents` 创建文档
- `GET    /api/v1/documents/{document_id}` 查看文档
- `PATCH  /api/v1/documents/{document_id}/status` 更新文档状态
- `GET    /api/v1/documents` 文档列表

### 条款
- `POST   /api/v1/documents/{document_id}/clauses/batch` 批量新增条款
- `POST   /api/v1/documents/{document_id}/clauses/import` 幂等导入条款
- `GET    /api/v1/documents/{document_id}/clauses` 按文档查看条款及最新意见
- `POST   /api/v1/clauses/{clause_id}/deprecate` 废弃条款

### 审阅意见
- `POST   /api/v1/clauses/{clause_id}/comments` 添加审阅意见
- `PATCH  /api/v1/comments/{comment_id}/status` 变更意见状态
- `GET    /api/v1/comments/unresolved?risk_level=critical` 按风险等级查询未处理意见（未处理 = `open`/`accepted`；`rejected`/`resolved` 不计入）
- `POST   /api/v1/comments/{comment_id}/processing-records` 写入处理记录
- `GET    /api/v1/comments/{comment_id}/processing-history` 查看处理历史

### 风险标签
- `POST   /api/v1/risk-tags` 创建风险标签
- `GET    /api/v1/risk-tags` 标签列表
- `POST   /api/v1/risk-tags/clauses/{clause_id}/bindings` 绑定标签到条款
- `GET    /api/v1/risk-tags/clauses/{clause_id}/bindings` 查询条款绑定

### 版本复制
- `POST   /api/v1/documents/{document_id}/copy` 复制文档版本，返回复制结果（`clause_mappings`、`copied_tag_count`、`skipped_deprecated_count`、`skipped_resolved_comment_count`）
- `GET    /api/v1/document-copies/{target_document_id}/detail` 按目标文档查看复制详情（每个新条款对应的原条款、继承标签、已复制意见、未复制原因）
- `GET    /api/v1/document-copies` 查询全部复制映射
- `GET    /api/v1/documents/{document_id}/copy-mappings` 按源文档查询复制映射

### 看板
- `GET    /api/v1/dashboard/documents/{document_id}` 文档汇总看板
- `GET    /api/v1/dashboard/documents/{document_id}/risk?include_deprecated=false` 风险看板：各风险等级未处理/已解决数量、最高风险条款、带标签条款数、无标签高风险条款
- `GET    /api/v1/dashboard/risk-distribution` 按标签统计风险分布

### 一致性自检
- `GET    /api/v1/consistency/check` 台账一致性自检，返回统一报告

自检报告结构：

```json
{
  "passed": true,
  "total_checks": 7,
  "passed_checks": 7,
  "failed_checks": 0,
  "total_issues": 0,
  "checked_at": "2026-08-03T05:00:00Z",
  "checks": [
    { "name": "...", "passed": true, "issue_count": 0, "issues": [] }
  ]
}
```

每项检查包含 `name`、`passed`、`issue_count`、`issues`（明细列表）。自检覆盖：

1. `comments_on_deprecated_clauses`：意见是否挂在已废弃条款上
2. `resolved_comments_missing_processing_records`：resolved 意见是否缺少处理记录
3. `duplicate_tag_bindings`：条款标签是否重复绑定
4. `document_copy_mappings`：文档复制映射是否引用缺失文档
5. `dashboard_statistics_consistency`：看板总数与状态明细是否一致
6. `duplicate_clause_no_within_document`：同一文档下是否存在重复 clause_no
7. `unresolved_list_status_consistency`：rejected/resolved 意见是否仍出现在未处理列表中

### 健康检查
- `GET    /health`

## 关键业务规则

1. 同一文档下 `clause_no` 不允许重复（批量与导入均校验，请求内重复也会拒绝）。
2. 幂等导入的 `mode` 只能是 `skip_existing` 或 `update_existing`。
3. 已废弃（`deprecated=true`）的条款不能新增意见，也不能绑定新标签。
4. 意见状态迁移走状态机；`open→accepted/rejected`、`accepted→resolved` 自动写入处理记录。
5. 禁止从 `resolved` 回退到任何状态。
6. 复制文档版本时：
   - 只复制未废弃条款；
   - 复制条款的风险标签绑定（标签是条款的风险分类，不是意见状态）；
   - 只复制未解决（非 `resolved`）的意见；
   - 返回 `clause_mappings`（源/目标条款 ID、继承标签、复制/跳过意见数）及累计统计。
7. 风险看板（`/dashboard/documents/{id}/risk`）：
   - `resolved` 意见只计入已解决统计，不进入未处理统计；
   - 废弃条款默认不参与看板，传 `include_deprecated=true` 才纳入；
   - 返回各风险等级未处理/已解决数量、最高风险条款列表、带标签/无标签条款数量、无标签高风险条款列表。

## 错误码

| error_code | HTTP | 含义 |
|---|---|---|
| `not_found` | 404 | 资源不存在 |
| `conflict` | 409 | 唯一约束/重复绑定冲突 |
| `validation_error` | 422 | 请求参数校验失败 |
| `invalid_state_transition` | 409 | 意见状态机非法迁移 |
| `business_rule_violation` | 409 | 违反业务规则（如对废弃条款操作） |
| `internal_server_error` | 500 | 未预期异常 |

## 端到端操作流程

以下流程演示从创建文档到复制新版本的完整台账操作（假设服务运行在 `127.0.0.1:18103`）。

### 1. 创建文档

```bash
curl -X POST http://127.0.0.1:18103/api/v1/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Vendor Agreement",
    "source_department": "Procurement",
    "version_no": "1.0"
  }'
```

记录返回的 `id` 作为 `DOC_ID`。

### 2. 幂等导入条款

```bash
curl -X POST http://127.0.0.1:18103/api/v1/documents/$DOC_ID/clauses/import \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "update_existing",
    "clauses": [
      {"clause_no": "1", "clause_text": "Confidentiality", "importance": "high"},
      {"clause_no": "2", "clause_text": "Liability", "importance": "medium"}
    ]
  }'
```

响应包含 `created`/`updated`/`skipped` 计数以及 `id_mapping`（`old_id`/`final_id`）。

### 3. 添加审阅意见

```bash
curl -X POST http://127.0.0.1:18103/api/v1/clauses/$CLAUSE_ID/comments \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_name": "Alice",
    "comment_text": "Clarify data handling",
    "risk_level": "high"
  }'
```

新意见初始状态为 `open`。记录返回的 `id` 作为 `COMMENT_ID`。

### 4. 创建并绑定风险标签

```bash
TAG_ID=$(curl -s -X POST http://127.0.0.1:18103/api/v1/risk-tags \
  -H "Content-Type: application/json" \
  -d '{"name": "DataPrivacy", "description": "Personal data risk"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -X POST http://127.0.0.1:18103/api/v1/risk-tags/clauses/$CLAUSE_ID/bindings \
  -H "Content-Type: application/json" \
  -d "{\"tag_id\": $TAG_ID}"
```

标签是条款的风险分类，不是意见状态。

### 5. 处理意见（状态机）

```bash
curl -X PATCH http://127.0.0.1:18103/api/v1/comments/$COMMENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{"process_status": "accepted", "operator": "Bob", "note": "acknowledged"}'

curl -X PATCH http://127.0.0.1:18103/api/v1/comments/$COMMENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{"process_status": "resolved", "operator": "Bob", "note": "fixed"}'
```

`open→accepted`、`open→rejected`、`accepted→resolved` 会自动写入处理记录。查看历史：

```bash
curl http://127.0.0.1:18103/api/v1/comments/$COMMENT_ID/processing-history
```

### 6. 查看风险看板

```bash
curl "http://127.0.0.1:18103/api/v1/dashboard/documents/$DOC_ID/risk"
```

`resolved`/`rejected` 意见计入已解决统计，不计入未处理；废弃条款默认排除，加 `?include_deprecated=true` 可纳入。

### 7. 复制文档新版本

```bash
curl -X POST http://127.0.0.1:18103/api/v1/documents/$DOC_ID/copy \
  -H "Content-Type: application/json" \
  -d '{"new_version_no": "2.0"}'
```

复制只包含未废弃条款、其风险标签绑定和未解决意见。响应返回 `clause_mappings`、`copied_tag_count`、`skipped_deprecated_count`、`skipped_resolved_comment_count`。记录返回的 `target_document_id` 作为 `NEW_DOC_ID`。

查看复制详情：

```bash
curl http://127.0.0.1:18103/api/v1/document-copies/$NEW_DOC_ID/detail
```

### 8. 台账自检

```bash
curl http://127.0.0.1:18103/api/v1/consistency/check
```

返回 `passed`、`checks` 数组（每项含 `name`、`passed`、`issue_count`、`issues`），用于验收前核验台账自洽性。

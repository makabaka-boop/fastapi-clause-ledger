# fastapi-clause-ledger

合规条款审阅台账服务，面向合规团队结构化沉淀制度文本与合同条款的审阅意见，追踪风险标签、处理过程与文档版本复制关系。

纯后端实现，基于 **FastAPI + SQLAlchemy 2.0 + SQLite + Pydantic v2**，服务监听 **18103** 端口，默认 SQLite 数据库文件为项目根目录下的 `clause_ledger.db`。

## 分层架构

```
app/
├── main.py                 # FastAPI 应用入口、生命周期、路由挂载
├── config.py               # 配置（端口、数据库、API 前缀）
├── database.py             # 引擎 / Session / Base / init_db
├── enums.py                # RiskLevel / ProcessStatus / DocumentStatus / ImportMode
├── utils.py                # UTC 时间与 ISO 8601 序列化
├── models/                 # SQLAlchemy ORM 数据模型
│   ├── document.py
│   ├── clause.py
│   ├── comment.py
│   ├── tag.py
│   ├── tag_binding.py
│   ├── process_record.py
│   └── copy_mapping.py     # 文档级 + 条款级复制映射
├── schemas/                # Pydantic 请求/响应模型（snake_case）
├── repositories/           # 仓储层：纯数据访问
├── services/               # 服务层：业务规则与事务编排
│   └── consistency_service.py  # 台账一致性自检
├── state_machine/          # 意见处理状态机
│   └── comment_state.py
├── api/
│   ├── deps.py             # 依赖注入
│   └── v1/                 # /api/v1 路由
│       └── consistency.py  # 自检接口
└── exceptions/             # 业务异常 + 统一错误处理
tests/                      # pytest + TestClient
```

## 数据模型

- **documents**：`title`、`source_department`、`version_no`、`document_status`、`created_at`
- **clauses**：`document_id`、`clause_no`、`clause_text`、`clause_type`、`importance`、`deprecated`
  - 同一文档下 `(document_id, clause_no)` 唯一
- **comments**（审阅意见）：`clause_id`、`reviewer_name`、`comment_text`、`risk_level`、`process_status`、`created_at`
- **tags**：风险标签，`name` 唯一
- **tag_bindings**：条款与标签多对多绑定
- **process_records**：意见处理记录 `from_status` / `to_status` / `note` / `operator`
- **copy_mappings / clause_copy_mappings**：文档版本复制映射与条款级映射

## 业务规则

1. 同一文档下 `clause_no` 不允许重复。
2. 幂等导入 `mode` 只能为 `skip_existing` 或 `update_existing`：
   - `skip_existing`：返回 `created` 与 `skipped` 数量；
   - `update_existing`：返回 `created` 与 `updated` 数量；
   - 两种模式均在响应 `id_mappings` 中返回每条条款的 `clause_no`、`old_clause_id`（新增为 `null`）、`final_clause_id` 与 `action`（`created`/`updated`/`skipped`）。
3. 已废弃条款不能新增审阅意见、不能绑定新标签，且其上未处理意见（`open`/`accepted`）不能再变更状态；历史意见、历史标签与处理记录仍可查询。
4. 意见状态机：
   - `open → accepted`、`open → rejected`、`accepted → resolved` 必须写入处理记录。
   - `rejected` 与 `resolved` 均为终态，禁止回退（含回到 `open`）。
   - 非法迁移返回 `409 invalid_state_transition`。
5. 复制文档版本：
   - 只复制未废弃条款及其风险标签绑定。
   - 不复制已废弃条款。
   - 不复制审阅意见（含已解决意见）。
   - 记录文档级与条款级复制映射。

## 风险等级与处理状态

- `risk_level`：`low` / `medium` / `high` / `critical`
- `process_status`：`open` / `accepted` / `rejected` / `resolved`

## 统一约定

- 所有接口前缀：`/api/v1`
- 字段命名：`snake_case`
- 时间格式：ISO 8601 UTC（如 `2026-08-03T05:22:01.540607Z`）
- 错误响应固定结构：

```json
{ "error_code": "...", "message": "...", "details": { } }
```

## 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/documents` | 创建文档 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/documents/{id}` | 文档详情 |
| PATCH | `/api/v1/documents/{id}/status` | 更新文档状态 |
| POST | `/api/v1/documents/{id}/clauses/batch` | 批量新增条款 |
| POST | `/api/v1/documents/{id}/clauses/import` | 幂等导入条款 |
| GET | `/api/v1/documents/{id}/clauses` | 文档下条款列表 |
| POST | `/api/v1/documents/{id}/clauses/{clause_id}/deprecate` | 废弃条款 |
| POST | `/api/v1/clauses/{clause_id}/comments` | 添加审阅意见 |
| GET | `/api/v1/documents/{id}/clauses/latest-comments` | 按文档查看条款及最新意见 |
| GET | `/api/v1/comments/unresolved?risk_level=...` | 按风险等级查询未处理意见 |
| GET | `/api/v1/comments/{id}` | 意见详情 |
| PATCH | `/api/v1/comments/{id}/status` | 变更意见状态（自动写处理记录） |
| POST | `/api/v1/comments/{id}/process-records` | 写入处理记录（备注） |
| GET | `/api/v1/comments/{id}/process-records` | 查看处理历史 |
| POST | `/api/v1/tags` | 创建风险标签 |
| GET | `/api/v1/tags` | 标签列表 |
| GET | `/api/v1/tags/{id}` | 标签详情 |
| POST | `/api/v1/tags/bindings` | 绑定标签到条款 |
| GET | `/api/v1/tags/risk-distribution` | 按标签统计风险分布 |
| POST | `/api/v1/documents/{id}/copy` | 复制文档版本 |
| GET | `/api/v1/documents/{id}/copy-detail` | 按目标文档查看复制结果详情 |
| GET | `/api/v1/copy-mappings` | 查询复制映射 |
| GET | `/api/v1/copy-mappings/{id}` | 复制映射详情 |
| GET | `/api/v1/dashboard/documents/{id}` | 文档风险看板 |
| GET | `/api/v1/dashboard/documents/{id}/risk?include_deprecated=` | 风险看板（未处理分布、已解决、最高风险条款、带标签数、无标签高风险） |
| GET | `/api/v1/consistency/check` | 台账一致性自检 |

### 复制响应字段

`POST /documents/{id}/copy` 返回：

```json
{
  "source_document_id": 1,
  "target_document_id": 2,
  "copied_clauses": 2,
  "copied_tag_count": 3,
  "skipped_deprecated_count": 1,
  "skipped_resolved_comment_count": 1,
  "copy_mapping_id": 1,
  "clause_mappings": [
    {"source_clause_id": 1, "target_clause_id": 4, "clause_no": "1.1", "copied_tag_ids": [1]}
  ]
}
```

- `copied_tag_count`：继承的标签绑定总数（标签是条款风险分类，不是意见状态）。
- `skipped_deprecated_count`：源文档中因废弃而未复制的条款数。
- `skipped_resolved_comment_count`：被复制条款上已解决意见的数量（意见一律不复制，仅统计已解决意见作为风险继承参考）。
- `clause_mappings`：每个新条款对应的原条款 ID 与继承的标签 ID。

`GET /documents/{target_id}/copy-detail` 按目标文档返回每个新条款对应的原条款、继承的风险标签（含标签名）、源条款已解决意见数，以及因废弃而跳过的条款与原因。

### 风险看板口径

`GET /dashboard/documents/{id}/risk`：

- `unresolved_by_risk`：按 `low/medium/high/critical` 统计**未处理**意见数（`open`/`accepted` 计入；`resolved` 与 `rejected` 均不计入）。
- `resolved_count`：已解决意见数。
- `highest_risk_clauses`：按条款下未处理意见的最高风险等级降序排列。
- `tagged_clause_count`：至少绑定一个风险标签的条款数。
- `untagged_high_risk_clauses`：存在高风险/严重未处理意见但未绑定任何标签的条款。
- 废弃条款默认不参与看板统计；传 `include_deprecated=true` 可显式包含。

### 一致性自检

`GET /consistency/check` 校验审阅台账是否自洽，返回统一 JSON，按 `checks` 数组列出每项检查的名称、通过状态、问题数量和明细：

```json
{
  "all_passed": true,
  "total_checks": 7,
  "failed_checks": 0,
  "checks": [
    {"check_name": "duplicate_clause_no", "passed": true, "issue_count": 0, "details": []}
  ]
}
```

| 检查名称 | 说明 |
| --- | --- |
| `comments_on_deprecated_clauses` | 意见是否指向已废弃条款 |
| `resolved_comments_missing_records` | resolved 意见是否缺少处理记录 |
| `duplicate_tag_bindings` | 条款标签是否重复绑定 |
| `missing_copy_mappings` | 文档复制映射是否缺失或存在未映射的目标条款 |
| `dashboard_stats_consistency` | 看板统计与明细数量是否一致 |
| `duplicate_clause_no` | 同一文档下是否存在重复 clause_no |
| `terminal_comments_in_unresolved` | resolved/rejected 意见是否仍被计入未处理列表 |

## 完整操作流程

以下流程从创建文档到复制新版本，可直接用 curl 执行（对应测试见 `tests/test_readme_flow.py`）：

```bash
B=http://localhost:18103/api/v1

# 1. 创建文档并更新状态
curl -X POST $B/documents -H "Content-Type: application/json" \
  -d '{"title":"MSA","source_department":"Legal","version_no":"v1.0"}'
curl -X PATCH $B/documents/1/status -H "Content-Type: application/json" \
  -d '{"document_status":"in_review"}'

# 2. 幂等导入条款（update_existing 模式，返回 id_mappings 旧ID→最终ID）
curl -X POST $B/documents/1/clauses/import -H "Content-Type: application/json" \
  -d '{"mode":"update_existing","clauses":[
    {"clause_no":"1.1","clause_text":"Party A shall indemnify.","clause_type":"indemnity","importance":5},
    {"clause_no":"2.1","clause_text":"Governed by local law.","clause_type":"governing_law","importance":3}
  ]}'

# 3. 添加审阅意见
curl -X POST $B/clauses/1/comments -H "Content-Type: application/json" \
  -d '{"reviewer_name":"Alice","comment_text":"Missing cap.","risk_level":"high"}'

# 4. 创建风险标签并绑定到条款（标签是条款风险分类，不是意见状态）
curl -X POST $B/tags -H "Content-Type: application/json" -d '{"name":"indemnity-risk"}'
curl -X POST $B/tags/bindings -H "Content-Type: application/json" \
  -d '{"clause_id":1,"tag_id":1}'

# 5. 处理意见：open -> accepted -> resolved（每次合法迁移自动写处理记录）
curl -X PATCH $B/comments/1/status -H "Content-Type: application/json" \
  -d '{"process_status":"accepted","note":"Will add cap","operator":"Bob"}'
curl -X PATCH $B/comments/1/status -H "Content-Type: application/json" \
  -d '{"process_status":"resolved","note":"Cap added","operator":"Bob"}'
curl $B/comments/1/process-records

# 6. 复制文档新版本（只复制未废弃条款及其标签，不复制意见）
curl -X POST $B/documents/1/copy -H "Content-Type: application/json" \
  -d '{"new_version_no":"v2.0","copied_by":"Alice"}'

# 7. 查看复制详情与风险看板
curl $B/documents/2/copy-detail
curl "$B/dashboard/documents/1/risk"

# 8. 一致性自检
curl $B/consistency/check
```

## 快速开始

```bash
pip install -r requirements.txt

# 启动服务（监听 0.0.0.0:18103）
python -m uvicorn app.main:app --host 0.0.0.0 --port 18103
# 或
python -m app.main

# 健康检查
curl http://localhost:18103/api/v1/health
```

可通过环境变量覆盖配置：

- `APP_HOST`（默认 `0.0.0.0`）
- `APP_PORT`（默认 `18103`）
- `DATABASE_URL`（默认 `sqlite:///./clause_ledger.db`）

## 运行测试

```bash
python -m pytest -q
```

测试使用独立的临时 SQLite 数据库，每个用例自动重建表结构。

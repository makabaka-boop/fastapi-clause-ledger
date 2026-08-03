# fastapi-clause-ledger

合规条款审阅台账服务（Compliance Clause-Review Ledger）。面向合规团队，用于沉淀制度文本与合同条款的审阅意见，并追踪风险标签、处理过程和文档版本复制关系。纯后端 API，基于 **FastAPI + SQLite**，分层清晰（路由 / 服务 / 仓储 / 状态机 / 异常）。

服务监听端口 **18103**，所有业务接口以 **`/api/v1`** 开头，字段统一 **snake_case**，时间统一 **ISO 8601** 字符串。

---

## 快速开始

```bash
pip install -r requirements.txt

# 启动服务（默认 0.0.0.0:18103）
python -m app.main
# 或
uvicorn app.main:app --host 0.0.0.0 --port 18103

# 运行测试
python -m pytest tests/ -q
```

健康检查：

```bash
curl http://127.0.0.1:18103/health      # {"status":"ok"}
```

---

## 目录结构

```
app/
  config.py          运行配置（端口、DB 路径、API 前缀）
  enums.py           受控词表（文档状态/条款类型/重要度/风险等级/处理状态/导入模式）
  database.py        SQLite 连接、建表 SQL、事务上下文
  exceptions.py      异常层级 + 统一错误响应处理器
  state_machine.py   审阅意见处理状态机（open/accepted/rejected/resolved）
  schemas.py         Pydantic 请求/响应模型（全 snake_case）
  repositories.py    仓储层：所有 SQL 都在这里
  services.py        服务层：业务规则与编排
  routers.py         路由层：HTTP <-> schema，按资源分组
  main.py            应用工厂 + 入口
tests/
  conftest.py        独立临时 DB 的 TestClient fixture
  test_api.py        端到端接口/规则测试
```

## 数据模型（SQLite）

| 表 | 说明 | 关键字段 |
|---|---|---|
| `documents` | 文档 | title, source_department, version_no, document_status, created_at |
| `clauses` | 条款 | document_id, clause_no, clause_text, clause_type, importance, deprecated, deprecated_at；`(document_id, clause_no)` 唯一 |
| `reviews` | 审阅意见 | clause_id, reviewer_name, comment_text, risk_level, process_status, created_at |
| `risk_tags` | 风险标签 | name(唯一), description, created_at |
| `clause_tags` | 标签绑定 | clause_id, tag_id；`(clause_id, tag_id)` 唯一 |
| `process_records` | 处理记录 | review_id, from_status, to_status, operator, note, created_at |
| `document_copies` | 文档复制映射 | source_document_id, target_document_id, copied_tag_count, skipped_deprecated_count, skipped_resolved_comment_count, created_at |
| `copy_clause_map` | 复制条款溯源 | copy_id, source_clause_id, target_clause_id, created_at |

### 受控词表

- **document_status**：`draft` / `under_review` / `approved` / `archived`
- **clause_type**：`obligation` / `right` / `prohibition` / `definition` / `other`
- **importance**：`low` / `normal` / `high`
- **risk_level**：`low` / `medium` / `high` / `critical`
- **process_status**：`open` / `accepted` / `rejected` / `resolved`
- **import mode**：`skip_existing` / `update_existing`

---

## 接口一览（前缀 `/api/v1`）

| 方法 & 路径 | 功能 |
|---|---|
| `POST /documents` | 创建文档 |
| `GET /documents/{id}` | 查看文档 |
| `PATCH /documents/{id}/status` | 更新文档状态 |
| `POST /documents/{id}/clauses` | 批量新增条款 |
| `POST /documents/{id}/clauses/import` | 幂等导入条款（skip/update） |
| `GET /documents/{id}/clauses` | 按文档查看条款及最新意见 |
| `GET /documents/{id}/dashboard` | 文档风险看板（总量口径） |
| `GET /documents/{id}/risk-board?include_deprecated=` | 风险看板（未处理/已解决、最高风险、标签口径） |
| `POST /documents/{id}/copies` | 复制文档版本 |
| `GET /documents/{id}/copies` | 查询复制映射 |
| `GET /documents/{id}/copy-detail` | 复制结果详情（按目标文档，逐条款溯源） |
| `POST /clauses/{id}/deprecate` | 废弃条款 |
| `POST /clauses/{id}/reviews` | 添加审阅意见 |
| `POST /clauses/{id}/tags` | 绑定标签 |
| `PATCH /reviews/{id}/status` | 变更意见状态 |
| `POST /reviews/{id}/process-records` | 写入处理记录 |
| `GET /reviews/{id}/process-records` | 查看处理历史 |
| `GET /reviews/unprocessed?risk_level=` | 按风险等级查询未处理意见 |
| `POST /risk-tags` | 创建风险标签 |
| `GET /risk-tags/{id}/risk-distribution` | 按标签统计风险分布 |
| `GET /consistency-check` | 台账一致性自检 |
| `GET /health`（无前缀） | 健康检查 |

---

## 业务规则

1. **条款唯一性**：同一文档下 `clause_no` 不允许重复（请求体内重复也拒绝）。
2. **幂等导入**：`mode` 只能是 `skip_existing`（跳过已存在）或 `update_existing`（覆盖已存在内容）；均可安全重复执行。响应固定返回：
   - `skip_existing`：`skipped_count`（跳过数量）+ `created_count`（新增数量）；
   - `update_existing`：`updated_count`（更新数量）+ `created_count`（新增数量）；
   - `mapping`：每条提交的 `clause_no` 均给出 `action`（created/updated/skipped）、`previous_clause_id`（旧条款 ID，新增时为 `null`）与 `final_clause_id`（最终条款 ID）。更新/跳过时复用原行，故旧 ID 与最终 ID 相同，调用方始终能把旧引用解析到最终条款。

   响应示例：

   ```json
   {
     "mode": "update_existing",
     "created_count": 1,
     "updated_count": 1,
     "skipped_count": 0,
     "created": [ ... ],
     "updated": [ ... ],
     "skipped": [],
     "mapping": [
       {"clause_no": "C-1", "action": "updated", "previous_clause_id": 1, "final_clause_id": 1},
       {"clause_no": "C-2", "action": "created", "previous_clause_id": null, "final_clause_id": 5}
     ]
   }
   ```
3. **废弃条款守卫**：条款废弃后——
   - **历史仍可查**：历史意见、历史标签绑定、按标签的风险统计均保持可查询；
   - **新增被拒**：不能新增审阅意见（`rule_violation`）、不能绑定新标签（`rule_violation`）；
   - **冻结未处理意见**：处于 `open` 的意见不能再变更状态（`PATCH /reviews/{id}/status` 与写处理记录均返回 `rule_violation`）；已在处理中（`accepted`）的意见仍可正常收尾至 `resolved`。
4. **状态机**（校验首轮定义的 `process_status`）：
   - `open → accepted` / `open → rejected` **必须写处理记录**；
   - `accepted → resolved` **必须写处理记录**；
   - `rejected` 与 `resolved` 均为终态，**不能回到 `open`**（禁止回退）；
   - 未列出的迁移一律拒绝。
   - 需要处理记录的迁移（`PATCH /reviews/{id}/status`）必须携带 `operator`，否则返回 422。
   - 显式写处理记录（`POST /reviews/{id}/process-records`）时 `from_status` 必须等于意见当前状态，否则返回 422 且不落库。
5. **文档版本复制**：只复制**未废弃条款**及其**风险标签绑定**（标签是条款的风险分类，不是意见状态）；不复制已废弃条款，也不复制任何审阅意见（含已解决意见）。`POST /documents/{id}/copies` 响应固定返回：
   - `source_document_id`、`target_document_id`；
   - `clause_mappings`：每个新条款的 `source_clause_id` / `target_clause_id` / `clause_no` 及 `inherited_tags`（继承的风险标签）；
   - `copied_tag_count`（复制的标签绑定数）、`skipped_deprecated_count`（跳过的废弃条款数）、`skipped_resolved_comment_count`（跳过的已解决意见数）。

   `GET /documents/{target_id}/copy-detail` 按目标文档返回每个新条款对应的**原条款**、**继承的风险标签**与**未复制原因摘要**（`not_copied_summary`，例如源条款上未随版本复制的审阅意见数量）。

6. **风险看板 `GET /documents/{id}/risk-board`**（统计口径）：
   - `risk_breakdown`：各风险等级的 `unprocessed_count`（仅统计 `open` 意见）与 `resolved_count`（`resolved` 意见）；**`resolved` 意见绝不计入未处理**；
   - `top_risk_clauses`：按最高风险等级降序的条款列表；
   - `tagged_clause_count`：带风险标签的条款数量；
   - `untagged_high_risk_clauses`：最高风险为 `high`/`critical` 但未绑定任何风险标签的条款（风险分类缺口）；
   - 废弃条款默认不参与看板，仅当 `include_deprecated=true` 时纳入。

7. **一致性自检 `GET /consistency-check`**：只读审计整个台账，返回统一 JSON —— `healthy`、`total_problems`、`generated_at`（ISO 8601）与 `checks` 数组；每个检查项包含 `name`、`passed`、`problem_count`、`details`。检查项如下：
   - `reviews_added_after_deprecation`：意见是否指向条款被废弃之后新增的操作；
   - `tags_bound_after_deprecation`：标签是否在条款废弃之后才绑定；
   - `resolved_reviews_without_process_record`：`resolved` 意见是否缺少处理记录；
   - `duplicate_tag_bindings`：条款标签是否重复绑定；
   - `missing_copy_mappings`：文档复制映射是否缺失；
   - `dashboard_detail_mismatch`：看板统计与明细数量是否不一致；
   - `duplicate_clause_no`：同一文档下是否存在重复 `clause_no`；
   - `non_open_reviews_in_unprocessed`：`resolved`/`rejected` 意见是否仍会被计入未处理列表。

---

## 完整操作流程

从创建文档到复制新版本的端到端流程（示例使用 `curl`，默认端口 18103）：

```bash
BASE=http://127.0.0.1:18103/api/v1

# 1. 创建文档
DOC=$(curl -s -X POST $BASE/documents \
  -H 'Content-Type: application/json' \
  -d '{"title":"Vendor MSA","source_department":"Legal","version_no":"v1"}')
DOC_ID=$(echo "$DOC" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2. 导入条款（幂等；skip_existing / update_existing）
curl -s -X POST $BASE/documents/$DOC_ID/clauses/import \
  -H 'Content-Type: application/json' \
  -d '{"mode":"update_existing","clauses":[
        {"clause_no":"C-1","clause_text":"vendor shall indemnify","clause_type":"obligation","importance":"high"}]}'

# 3. 添加审阅意见（clause_id 取自上一步返回的 mapping.final_clause_id，此处假设为 1）
curl -s -X POST $BASE/clauses/1/reviews \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_name":"Alice","comment_text":"needs liability cap","risk_level":"high"}'

# 4. 创建并绑定风险标签
TAG=$(curl -s -X POST $BASE/risk-tags -H 'Content-Type: application/json' -d '{"name":"PII"}')
TAG_ID=$(echo "$TAG" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST $BASE/clauses/1/tags -H 'Content-Type: application/json' -d "{\"tag_id\":$TAG_ID}"

# 5. 处理意见：open -> accepted -> resolved（均需写处理记录，携带 operator）
curl -s -X PATCH $BASE/reviews/1/status -H 'Content-Type: application/json' \
  -d '{"to_status":"accepted","operator":"Alice"}'
curl -s -X PATCH $BASE/reviews/1/status -H 'Content-Type: application/json' \
  -d '{"to_status":"resolved","operator":"Alice"}'

# 6. 复制文档新版本（只复制未废弃条款及其标签，不复制意见）
curl -s -X POST $BASE/documents/$DOC_ID/copies -H 'Content-Type: application/json' \
  -d '{"version_no":"v2"}'

# 7. 查看风险看板 / 复制详情 / 运行一致性自检
curl -s "$BASE/documents/$DOC_ID/risk-board"
curl -s "$BASE/documents/2/copy-detail"        # 2 = 复制生成的目标文档 id
curl -s "$BASE/consistency-check"
```

---

## 错误响应

所有错误固定为如下结构：

```json
{
  "error_code": "conflict",
  "message": "clause_no 'C-1' already exists in document 1.",
  "details": {"document_id": 1, "clause_no": "C-1"}
}
```

| error_code | HTTP | 场景 |
|---|---|---|
| `validation_error` | 422 | 请求体/业务校验失败（含枚举非法、批内重复、缺 operator） |
| `not_found` | 404 | 资源不存在 |
| `conflict` | 409 | 唯一性冲突（重复 clause_no / 标签名 / 标签绑定） |
| `invalid_transition` | 409 | 非法状态迁移 / rejected、resolved 回退 |
| `rule_violation` | 409 | 对废弃条款新增意见、绑定新标签或变更其未处理意见状态 |
| `internal_error` | 500 | 未预期异常 |

---

## 配置项（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `CLAUSE_LEDGER_HOST` | `0.0.0.0` | 监听地址 |
| `CLAUSE_LEDGER_PORT` | `18103` | 监听端口 |
| `CLAUSE_LEDGER_DB` | `./clause_ledger.db` | SQLite 文件路径（测试使用临时文件） |

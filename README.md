# fastapi-clause-ledger

合规条款审阅台账服务，面向合规团队管理文档、条款、风险标签、审阅意见、处理记录、版本复制和风险看板，重点考察 FastAPI 分层、Pydantic 校验、SQLite 关系建模和审计一致性。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 18103
```

- 服务监听 `18103` 端口，业务接口统一以 `/api/v1` 开头，健康检查为 `GET /health`。
- 数据库默认为项目根目录下的 SQLite 文件 `clause_ledger.db`，可用环境变量 `CLAUSE_LEDGER_DATABASE_URL` 覆盖。
- 字段命名统一 snake_case，响应时间统一 ISO 8601 字符串。
- 交互式文档：`http://localhost:18103/docs`。

## 运行测试

```bash
.venv/bin/python -m pytest tests/ -q
```

## 项目结构

```
app/
├── main.py                # 应用入口、全局异常处理（统一错误格式）
├── config.py              # 配置（端口、数据库地址）
├── constants.py           # 枚举常量（风险等级/处理状态/导入模式等）
├── database.py            # SQLAlchemy 引擎与会话
├── models.py              # ORM 数据模型（7 张表）
├── schemas.py             # Pydantic 请求/响应模型（snake_case）
├── exceptions.py          # 业务异常定义
├── state_machine.py       # 审阅意见处理状态机
├── repositories/          # 仓储层：documents/clauses/reviews/tags/records/copies
├── services/              # 服务层：业务规则与事务
└── routers/               # 路由层：documents/clauses/reviews/tags
tests/
└── test_api.py            # 端到端测试（20 个用例）
```

## 数据模型

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| documents | 制度/合同文档 | title, source_department, version_no, document_status, created_at |
| clauses | 条款 | document_id, clause_no, clause_text, clause_type, importance, deprecated |
| reviews | 审阅意见 | clause_id, reviewer_name, comment_text, risk_level, process_status, created_at |
| risk_tags | 风险标签 | tag_name, description |
| clause_tag_bindings | 条款-标签绑定 | clause_id, tag_id（唯一约束） |
| process_records | 处理记录 | review_id, from_status, to_status, operator_name, note |
| document_copy_mappings | 文档复制映射 | source_document_id, target_document_id, 各项复制统计 |
| copy_items | 复制明细 | mapping_id, item_type, action, source/target_clause_id, reason, inherited_tag_ids |

约束：`(document_id, clause_no)` 唯一；`risk_level ∈ {low, medium, high, critical}`；`process_status ∈ {open, accepted, rejected, resolved}`。

## 接口一览（/api/v1）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /documents | 创建文档 |
| GET | /documents | 文档列表 |
| PATCH | /documents/{id}/status | 更新文档状态 |
| POST | /documents/{id}/clauses/batch | 批量新增条款 |
| POST | /documents/{id}/clauses/import | 幂等导入条款（mode=skip_existing/update_existing） |
| GET | /documents/{id}/clauses | 按文档查看条款及最新意见与标签 |
| POST | /documents/{id}/copy | 复制文档版本（返回 clause_mappings 与各项计数） |
| GET | /documents/{id}/copy_details | 复制结果详情：新条款对应原条款、继承标签、未复制原因 |
| GET | /documents/{id}/risk_dashboard | 文档风险看板（?include_deprecated=true 可含废弃条款） |
| POST | /clauses/{id}/deprecate | 废弃条款 |
| POST | /clauses/{id}/reviews | 添加审阅意见 |
| GET | /clauses/{id}/reviews | 查看条款历史意见（含已废弃条款） |
| POST | /clauses/{id}/tags | 绑定风险标签 |
| GET | /reviews?risk_level=... | 按风险等级查询未处理（open）意见 |
| POST | /reviews/{id}/status | 变更意见状态（自动写处理记录） |
| POST | /reviews/{id}/records | 写入处理记录 |
| GET | /reviews/{id}/records | 查看处理历史 |
| POST | /tags | 创建风险标签 |
| GET | /tags | 标签列表 |
| GET | /tags/{id}/risk_distribution | 按标签统计风险分布 |
| GET | /copies?document_id=... | 查询复制映射 |
| GET | /consistency/checks | 台账一致性自检 |
| GET | /health | 健康检查 |

## 核心业务规则

1. **clause_no 唯一**：同一文档下 `clause_no` 不允许重复，冲突返回 409 `duplicate_clause_no`。
2. **幂等导入**：`mode` 仅允许 `skip_existing`（已存在则跳过）或 `update_existing`（已存在则更新），重复执行结果一致。响应包含 `created_count` / `skipped_count` / `updated_count` 计数及 `clause_id_mapping`（每项为 `{"old_clause_id", "final_clause_id", "action"}`，新增条款 `old_clause_id` 为 `null`）。
3. **废弃条款**：已废弃条款不能新增审阅意见、不能绑定新标签、不能变更其未处理意见状态或写入处理记录（均返回 409 `clause_deprecated`）；但历史意见（`GET /clauses/{id}/reviews`）与历史标签（随 `GET /documents/{id}/clauses` 返回）仍可查询。
4. **状态机**：合法流转为 `open → accepted / rejected`、`accepted → resolved`；这些流转必须写入处理记录；`rejected` 与 `resolved` 均为终态，禁止回退到 `open` 或任何其他状态（409 `invalid_status_transition`）。目标状态必须是首轮定义的 `process_status` 枚举值之一。
5. **版本复制**：只复制未废弃条款及其风险标签绑定和未解决意见；已废弃条款与已解决（resolved）意见不复制。复制响应返回 `source_document_id`、`target_document_id`、`clause_mappings`（新旧条款对应及 `inherited_tag_ids`）、`copied_tag_count`、`skipped_deprecated_count`、`skipped_resolved_comment_count`；逐条明细持久化在 `copy_items` 表，可通过 `GET /documents/{id}/copy_details` 按目标文档查询每个新条款的原条款、继承的风险标签和未复制原因摘要。
6. **风险看板**：按文档返回各风险等级未处理（open）数量、已解决（resolved）数量、最高风险条款列表、带标签条款数量、无标签高风险（high/critical）条款列表。resolved 意见不计入未处理统计；废弃条款默认不参与，`?include_deprecated=true` 时才纳入；标签是条款的风险分类（绑定在条款上），不作为意见状态参与统计。
7. **一致性自检**：`GET /api/v1/consistency/checks` 对台账做只读审计，返回 `{"overall_passed", "check_count", "failed_count", "checked_at", "checks": [{"check_name", "passed", "issue_count", "details"}]}`。七项检查：

   | check_name | 检查内容 |
   | --- | --- |
   | deprecated_clause_operations | 条款废弃后是否仍新增意见/标签绑定/处理记录 |
   | resolved_reviews_missing_process_record | resolved 意见是否缺少处理记录 |
   | duplicate_tag_bindings | 条款是否重复绑定同一标签 |
   | copy_mapping_integrity | 复制映射的源/目标文档是否存在 |
   | dashboard_consistency | 看板聚合数量与明细数量是否一致 |
   | duplicate_clause_no | 同一文档下是否存在重复 clause_no |
   | open_list_purity | resolved/rejected 是否混入未处理列表、状态值是否合法 |

## 错误响应格式

所有错误统一返回：

```json
{
  "error_code": "duplicate_clause_no",
  "message": "同一文档下 clause_no 不允许重复: 1.1",
  "details": {"document_id": 1, "clause_no": "1.1"}
}
```

主要错误码：`validation_error`(422)、`not_found`(404)、`duplicate_clause_no`(409)、`clause_deprecated`(409)、`duplicate_tag_binding`(409)、`invalid_status_transition`(409)、`invalid_import_mode`(422)。

## 完整操作流程

以下流程与自动化测试 `test_readme_flow_executable` 一一对应，可从零执行：

```bash
# 1. 创建文档
curl -X POST http://localhost:18103/api/v1/documents \
  -H 'Content-Type: application/json' \
  -d '{"title":"供应商管理制度","source_department":"合规部","version_no":"v1"}'

# 2. 批量新增条款，再幂等导入（update_existing：1.1 更新、1.2 新增）
curl -X POST http://localhost:18103/api/v1/documents/1/clauses/batch \
  -H 'Content-Type: application/json' \
  -d '{"clauses":[{"clause_no":"1.1","clause_text":"供应商准入须审批"}]}'
curl -X POST http://localhost:18103/api/v1/documents/1/clauses/import \
  -H 'Content-Type: application/json' \
  -d '{"mode":"update_existing","clauses":[{"clause_no":"1.1","clause_text":"供应商准入须两级审批"},{"clause_no":"1.2","clause_text":"年度复审"}]}'

# 3. 添加审阅意见（初始状态 open）
curl -X POST http://localhost:18103/api/v1/clauses/1/reviews \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_name":"张三","comment_text":"审批层级不足","risk_level":"high"}'

# 4. 创建风险标签并绑定到条款（标签 = 条款的风险分类）
curl -X POST http://localhost:18103/api/v1/tags \
  -H 'Content-Type: application/json' -d '{"tag_name":"流程风险"}'
curl -X POST http://localhost:18103/api/v1/clauses/1/tags \
  -H 'Content-Type: application/json' -d '{"tag_id":1}'

# 5. 处理意见：open -> accepted -> resolved（每次流转自动写处理记录）
curl -X POST http://localhost:18103/api/v1/reviews/1/status \
  -H 'Content-Type: application/json' -d '{"to_status":"accepted","operator_name":"李四","note":"确认"}'
curl -X POST http://localhost:18103/api/v1/reviews/1/status \
  -H 'Content-Type: application/json' -d '{"to_status":"resolved","operator_name":"李四","note":"已修订"}'
curl http://localhost:18103/api/v1/reviews/1/records   # 查看处理历史

# 6. 复制文档版本（resolved 意见不复制，标签随条款继承）
curl -X POST http://localhost:18103/api/v1/documents/1/copy \
  -H 'Content-Type: application/json' -d '{"version_no":"v2"}'
curl http://localhost:18103/api/v1/documents/2/copy_details   # 复制结果详情

# 7. 查看风险看板与一致性自检
curl http://localhost:18103/api/v1/documents/1/risk_dashboard
curl http://localhost:18103/api/v1/consistency/checks
```

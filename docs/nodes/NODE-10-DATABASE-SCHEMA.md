# NODE-10 — Database Schema

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-09, NODE-03  
> Produces: PostgreSQL schema、SQLAlchemy models、Alembic migrations、索引与租户隔离基础

---

## 1. 目标

把 Domain Model 映射到可迁移、可审计、支持并发和版本演进的 PostgreSQL schema。数据库是业务真相源；Agent checkpoint、Redis、Object Storage 均不能替代它。

## 2. Persistence Baseline

- PostgreSQL。
- SQLAlchemy 2 async。
- asyncpg driver。
- Alembic migrations。
- pgvector extension（P0 memory/knowledge/asset embeddings）。
- UTC timestamptz。
- JSONB 只用于扩展字段/快照，不用来逃避建模。

## 3. Schema 组织

P0 使用单 logical DB、按表名前缀/ORM module 分 bounded context，避免过早多 schema 权限复杂度。生产可启用 PostgreSQL RLS 作为 defense-in-depth，但 API authorization 仍必须存在。

## 4. 核心表

### Identity / Tenant

```text
users
organizations
organization_members
workspaces
workspace_members
sessions / auth_identities
```

### Project / Brand

```text
projects
project_members
brands
brand_palettes
brand_fonts
brand_logos
brand_rules
```

### Assets

```text
assets
asset_files
asset_previews
asset_metadata
asset_embeddings
asset_rights
```

### Design / Artifact

```text
design_documents
design_document_versions
artifact_branches
artifacts
artifact_versions
artifact_edges
artifact_files
artifact_provenance
```

### Agent / Workflow

```text
agent_runs
agent_run_steps
tasks
task_dependencies
approvals
generations
provider_requests
```

### Platform

```text
cost_ledger
usage_counters
idempotency_operations
outbox_events
inbox_events
audit_events
```

Memory/Knowledge 表在 NODE-35/36 扩展。

## 5. 通用列

大多数 mutable entity：

```text
id UUID PK
organization_id UUID NOT NULL
created_at timestamptz NOT NULL
updated_at timestamptz NOT NULL
version integer NOT NULL default 1
```

需要 optimistic concurrency 的对象使用 `version`，更新 SQL 必须带 expected version。

Immutable ledger/event/history 表不需要 `updated_at`。

## 6. Soft Delete

默认不全局 soft delete。

- Project/Asset 等用户可恢复对象：`deleted_at`。
- Ledger/Audit/Event：不可 delete。
- Ephemeral/derived cache：允许 hard delete。

避免所有查询都隐式忘记 `deleted_at`。

## 7. 关键表字段示例

### projects

```text
id
organization_id
workspace_id
name
status
brief_json
brand_id nullable
active_branch_id nullable
settings_json
created_by
created_at
updated_at
version
```

### tasks

```text
id
organization_id
project_id
parent_task_id nullable
type
status
owner_agent_key
input_json
output_json
priority
attempt_count
max_attempts
budget_reserved
started_at
finished_at
version
```

### artifact_versions

```text
id
organization_id
artifact_id
branch_id
parent_version_id nullable
version_number
status
content_hash
metadata_json
quality_score nullable
created_by_type
created_by_id
created_at
```

### cost_ledger

```text
id
organization_id
project_id nullable
task_id nullable
agent_run_id nullable
generation_id nullable
provider
model
entry_type
amount numeric(20,8)
currency char(3)
quantity numeric(30,10)
unit
provider_request_id nullable
occurred_at
metadata_json
```

金额禁止 float。

## 8. Lineage Graph

`artifact_edges`：

```text
from_artifact_version_id
to_artifact_version_id
edge_type
metadata_json
```

edge types：

```text
DERIVED_FROM
EDITED_FROM
COMPOSED_FROM
RESIZED_FROM
EXPORTED_FROM
GENERATED_FROM_ASSET
```

数据库约束 + service 检查防止自环；复杂环检测由 domain service 完成。

## 9. Task DAG

`task_dependencies` unique：

```text
(task_id, depends_on_task_id)
```

插入 dependency 前做 cycle detection。

## 10. Embedding

NODE-07 选定 P0 embedding dimension 后生成 typed vector column。记录：

```text
embedding_model
embedding_version
content_hash
embedding vector(N)
```

换 embedding model 时不要原地把旧 embedding 解释成新模型；新版本/新表或新 column/backfill。

## 11. Index Strategy

必须至少：

```text
organization_id
(project_id, created_at)
(project_id, status)
(artifact_id, version_number)
(task_id, status)
(agent_run_id, created_at)
(provider_request_id)
(idempotency_key unique scoped)
(outbox published_at, created_at)
```

JSONB 只有明确 query pattern 才加 GIN。

## 12. Tenant Isolation

所有 repository 查询必须显式 tenant scoped：

```sql
WHERE organization_id = :organization_id
```

生产 P1 可启 RLS：

```text
app.current_organization_id
```

但绝不把 RLS 当唯一 authorization。

## 13. Outbox / Inbox

同一 DB transaction：

```text
write domain rows
+ insert outbox event
COMMIT
```

dispatcher 异步发布；consumer 将 event_id 写 `inbox_events` 防重复。

## 14. Migration Rules

- migration 永不手改已在生产执行的历史 revision。
- Expand → migrate/backfill → switch → contract。
- 大表 migration 避免长时间 exclusive lock。
- destructive migration 必须有 backup/rollback plan。
- seed 与 migration 分离。

## 15. Fixtures

建立 deterministic seed：

```text
1 org
2 users
1 brand
2 projects
sample assets
sample DesignDocument
sample task graph
sample artifact lineage
```

不包含版权不明素材。

## 16. 测试

- Alembic from empty → head。
- downgrade 至少验证开发可回退的最近 revision。
- unique/FK/check constraints。
- tenant leak tests。
- optimistic lock conflict。
- ledger decimal precision。
- outbox atomicity。
- lineage/task cycle rejection。

## 17. 验收标准

- [ ] 空 DB migration 到 head 成功。
- [ ] Domain P0 entities 有 schema。
- [ ] 所有租户表有 organization_id。
- [ ] 金额 numeric，不使用 float。
- [ ] Outbox/Inbox 已建模。
- [ ] task/artifact graph 关系存在。
- [ ] sample seeds 可重复执行。
- [ ] tenant cross-read integration test 失败（按预期拒绝）。

## 18. Definition of Done

```text
schema + ORM + migrations committed
+ empty-db migration green
+ integration constraints green
+ ERD generated
```

下一节点：NODE-11 API Contract。

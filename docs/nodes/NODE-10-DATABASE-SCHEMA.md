# NODE-10 — Database Schema

> Phase: 1 Domain / Contract  
> Status: **VALIDATING**  
> Implementation Status: **IMPLEMENTED / POSTGRESQL CI PENDING**  
> Implementation Branch: `feat/node-10-database-schema`  
> Branch Base: `feat/node-09-domain-model` (stacked; NODE-09 is not yet merged)  
> Canonical Schema Contract: `docs/database/SCHEMA.md`  
> Acceptance Report: `reports/nodes/NODE-10/acceptance.md`  
> Implemented At: `2026-08-16`  
> Priority: P0  
> Depends on: NODE-09, NODE-03  
> Produces: PostgreSQL schema、SQLAlchemy mappings、Alembic migrations、RLS、索引、租户隔离与迁移验收

---

## 1. 目标

把 NODE-09 Domain Model 映射到可迁移、可审计、支持并发、租户隔离和版本演进的 PostgreSQL schema。数据库是业务真相源；Agent checkpoint、Redis、Object Storage 均不能替代它。

NODE-10 只做 persistence contract / schema，不反向修改领域语义。

## 2. Persistence Baseline

```text
PostgreSQL 17
pgvector extension
pgcrypto extension
SQLAlchemy 2 async mappings
asyncpg
Alembic
UTC timestamptz
JSONB for versioned/evolving payload boundaries
```

NODE-10 专项 workflow 固定验证工具版本：

```text
SQLAlchemy 2.0.51
Alembic 1.18.5
asyncpg 0.31.0
```

当前 repository frozen lock 仍不加入这些 runtime dependency；NODE-11 API/application persistence integration 必须同时更新 `apps/api/pyproject.toml` 与 `uv.lock`，不能为了 NODE-10 绕过 frozen-install gate。

## 3. Schema 组织

P0 使用单 logical database / `public` schema，按 SQLAlchemy module 划分 bounded context，避免过早拆 PostgreSQL schemas。

当前 P0：

```text
40 tables
37 tenant-owned tables
37 RLS policies
```

完整表清单见 `docs/database/SCHEMA.md`。

## 4. Core Table Groups

### Identity / Tenant

```text
users
organizations
organization_members
workspaces
workspace_members
auth_identities
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

### Agent / Workflow / Generation

```text
agent_runs
agent_run_steps
tasks
task_dependencies
approvals
idempotency_operations
generations
provider_requests
```

### Platform

```text
cost_ledger
usage_counters
outbox_events
inbox_events
audit_events
```

Memory/Knowledge persistence 在后续节点扩展，不在 NODE-10 提前混入。

## 5. Common Persistence Columns

大多数 mutable tenant entities：

```text
id UUID PK
organization_id UUID NOT NULL
created_at timestamptz NOT NULL
updated_at timestamptz NOT NULL
version integer NOT NULL default 1 CHECK version >= 1
```

Immutable history 使用 `created_at`，不伪装成可修改 entity。

NODE-09 的 UUIDv7 由 application 生成；数据库不使用 autoincrement business ID。

## 6. Optimistic Concurrency

Mutable aggregate 更新必须携带 expected version：

```sql
UPDATE ...
SET ..., version = version + 1
WHERE id = :id
  AND organization_id = :organization_id
  AND version = :expected_version;
```

`UPDATE 0` 表示 stale state 或不可见 row；application/service 不能 blind overwrite。

数据库 trigger 负责 `updated_at = now()`，不只依赖 ORM client-side behavior。

## 7. Soft Delete / Immutable History

Soft delete：

```text
brands
projects
assets
design_documents
artifacts
```

数据库禁止 UPDATE/DELETE：

```text
cost_ledger
audit_events
inbox_events
design_document_versions
artifact_provenance
```

`artifact_versions`：

- DELETE 永远拒绝；
- pre-approval state 可以按状态机推进；
- 一旦 `OLD.status = approved`，任何后续 UPDATE 拒绝；
- 修订必须新建 ArtifactVersion。

## 8. Exact Money / Usage

禁止 `float` / `real` / `double precision` 持久化金额。

```text
agent_runs.budget_amount       NUMERIC(20,8)
tasks.budget_reserved          NUMERIC(20,8)
cost_ledger.amount             NUMERIC(20,8)
cost_ledger.quantity           NUMERIC(30,10)
usage_counters.quantity        NUMERIC(30,10)
artifact_versions.quality_score NUMERIC(8,5)
```

静态 schema validator 会直接拒绝 SQLAlchemy `Float` 和 frozen SQL 中的浮点 SQL type。

## 9. Tenant Isolation

### Tenant columns

除以下 3 张 global/root table 外，全部 P0 table 必须有 non-null `organization_id`：

```text
users
organizations
auth_identities
```

### RLS

NODE-10 已把 RLS 提升为 P0 defense-in-depth，而不是推迟到 P1。

每个 tenant table：

```sql
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id())
```

`lumi_app` 受 RLS；`lumi_migration` 仅用于 schema/seed/migration，不用于 normal API request。

API membership authorization 仍然必须存在，RLS 不替代授权。

### Cross-tenant foreign references

仅校验 row 自己的 `organization_id` 不够。例如 tenant B row 仍可能错误引用 tenant A workspace。

NODE-10 增加 relationship trigger `lumi_enforce_same_tenant_fk()`。

该函数使用：

```text
SECURITY DEFINER
SET search_path = public, pg_temp
```

因为普通 invoker trigger 会被 RLS 隐藏另一个 tenant 的 referenced row，从而漏掉 cross-tenant FK。Definer 函数只用于 migration-controlled reference inspection，并锁死 search path。

DesignDocument 的 `head_version_id` 与 DesignDocumentVersion 的 `parent_version_id` 同样纳入 tenant guard。

## 10. Task DAG

`task_dependencies`：

```text
PK(task_id, depends_on_task_id)
CHECK task_id <> depends_on_task_id
same-tenant trigger
recursive cycle-rejection trigger
reverse dependency index
```

Domain service 仍先验证 DAG；DB trigger 防止 race/manual bypass。

## 11. Artifact Lineage

多父 lineage 由 `artifact_edges` 表达，不把单一 `parent_version_id` 锁死在 ArtifactVersion row 上。

支持：

```text
DERIVED_FROM
EDITED_FROM
COMPOSED_FROM
RESIZED_FROM
EXPORTED_FROM
GENERATED_FROM_ASSET
```

DB 拒绝：

```text
self edge
duplicate typed edge
cross-tenant endpoints
recursive lineage cycle
```

## 12. Design Document Versioning

```text
design_documents
  └─ head_version_id

design_document_versions
  ├─ version_number
  ├─ parent_version_id
  ├─ content_json
  └─ content_hash
```

Version rows immutable；root mutable pointer 指向 head。

## 13. Generation / Provider / Idempotency

`AgentRun`、`Generation`、`ProviderRequest` 保持分离：

```text
AgentRun = orchestration business run
Generation = paid/idempotent model operation
ProviderRequest = provider-native call/response identity
```

`idempotency_operations`：

```text
UNIQUE (organization_id, idempotency_key)
request_hash
operation_type
status
response_json
expires_at
```

重复 tenant/key 的付费 side effect 在 DB 层被拒绝。

## 14. Cost Ledger

`cost_ledger` append-only：

```text
charge      => related_entry_id NULL
reversal    => related_entry_id required
adjustment  => related_entry_id required
```

同时使用：

```text
immutable DB trigger
+ lumi_app UPDATE/DELETE REVOKE
```

避免错误代码把历史账目“修正”为新金额。

## 15. pgvector

当前 `asset_embeddings.embedding` 使用 generic PostgreSQL `vector`，同时保存：

```text
embedding_model
embedding_version
dimensions
content_hash
```

NODE-07 并没有冻结 production embedding dimension，因此 NODE-10 不伪造 `vector(N)`。后续模型/知识路由确定维度后再用 migration 增加 dimension/index contract。

## 16. Index Strategy

已实现关键 query-driven indexes：

```text
organization_id
(organization_id, project status / created_at)
(artifact_id, version_number)
(project_id, task status / created_at)
(project_id, agent_run created_at)
provider_request_id
(outbox published_at, created_at)
(cost_ledger organization_id, occurred_at)
artifact edge destination
task reverse dependency
```

JSONB 不无脑建立 GIN；等真实 query pattern 再加。

## 17. Outbox / Inbox

同 transaction：

```text
write domain rows
+ insert outbox event
COMMIT
```

`inbox_events(event_id, consumer)` 负责 consumer dedup，并作为 immutable processed history。

NODE-10 dynamic integration test 会故意在 project + outbox 同 transaction 中抛错，然后验证两者都 rollback。

## 18. Frozen Migration Strategy

首版 revision：

```text
20260816_0001
```

历史 revision 只读取自己的：

```text
20260816_0001_sql/up_01.sql ... up_08.sql
20260816_0001_sql/down_01.sql ... down_02.sql
```

禁止 revision import 当前 `Base.metadata` / `persistence.models`。

目的：未来 ORM 变化不会让历史 migration replay 产生不同 schema。

## 19. Seed

`apps/api/migrations/seeds/p0_local_fixture.sql` 提供 deterministic two-tenant fixture：

```text
2 organizations
2 users + memberships
2 workspaces
2 brands
2 projects
assets/files
task DAG
DesignDocument/version
Artifact/branch/version
idempotency operation
generation
exact Cost Ledger entry
```

seed 与 migration 分离，不包含版权素材。

## 20. Tests

### Static schema validator

`tools/node10/validate_schema.py`：

- exact 40-table inventory；
- 37 tenant columns；
- 37 RLS enable + 37 policies；
- exact money；
- PostgreSQL metadata compile；
- frozen migration isolation；
- pgvector/pgcrypto；
- immutable safeguards；
- tenant-reference guards；
- Task DAG / Artifact lineage guards；
- idempotency / outbox / inbox。

本地 fallback 已记录：

```text
LOCAL_SCHEMA_VALIDATION_PASS 40 37 94
COMPILEALL_PASS
```

见 `reports/nodes/NODE-10/local-schema-validation.txt`。

### Real PostgreSQL integration

`tools/node10/test_database_integration.py` 设计为验证 9 组真实 DB invariant：

1. Alembic revision applied；
2. tenant A/B RLS visibility；
3. cross-tenant reference rejection；
4. optimistic stale write；
5. exact Decimal + duplicate idempotency；
6. Task DAG cycle；
7. Artifact lineage cycle；
8. approved version + ledger immutability；
9. Project/Outbox atomic rollback。

### Migration lifecycle

`.github/workflows/node-10-database-schema.yml`：

```text
start PostgreSQL 17/pgvector
→ validate schema
→ alembic upgrade head
→ seed
→ integration tests
→ downgrade base
→ verify schema absent
→ upgrade head again
→ seed again
→ integration tests again
```

## 21. Acceptance Criteria

- [x] Domain P0 entities have explicit persistence schema.
- [x] 40-table P0 schema is frozen.
- [x] 37 tenant tables have mandatory organization_id.
- [x] RLS policies exist for all tenant tables.
- [x] Cross-tenant reference guard exists and is RLS-safe.
- [x] Money/usage uses NUMERIC, no persistence float.
- [x] Outbox/Inbox modeled.
- [x] Task/Artifact graphs modeled with DB cycle guards.
- [x] Immutable Ledger/Version history safeguards implemented.
- [x] Idempotency operation is tenant-scoped and unique.
- [x] deterministic two-tenant seed exists.
- [x] local deterministic schema validation passes.
- [ ] Empty PostgreSQL migration to head passes in repository-hosted gate.
- [ ] Dynamic tenant leak test passes (cross-read rejected).
- [ ] Dynamic cross-tenant reference test passes (write rejected).
- [ ] Dynamic optimistic lock / exact Decimal / idempotency tests pass.
- [ ] Dynamic DAG/lineage/immutability/outbox tests pass.
- [ ] Alembic downgrade → reapply test passes.
- [ ] Repository CI/security gates pass.
- [ ] NODE-09 base PR resolved and this stacked branch merged.
- [ ] `docs/NODE-INDEX.md` updated to COMPLETE.

## 22. Definition of Done

```text
schema + ORM mappings + frozen migrations
+ deterministic seed
+ RLS / same-tenant / exact money / concurrency
+ immutable history / idempotency / outbox
+ empty-db upgrade green
+ dynamic PostgreSQL invariants green
+ downgrade/reapply green
+ repository CI/security green
+ NODE-09 dependency merged
+ NODE-10 merged and index updated
```

当前状态：`VALIDATING`，不是 `COMPLETE`。

下一节点：NODE-11 API Contract。

# LUMI AI Design OS — PostgreSQL Schema V1

> Node: NODE-10  
> Status: IMPLEMENTED / VALIDATING  
> Date: 2026-08-16  
> Domain source: `docs/domain/DOMAIN-MODEL.md`  
> SQLAlchemy mappings: `apps/api/src/lumi_api/persistence/`  
> Frozen migration: `apps/api/migrations/versions/20260816_0001_p0_schema.py`

## 1. Purpose

NODE-10 translates the frozen NODE-09 business semantics into PostgreSQL persistence without letting ORM tables redefine the domain model.

The persistence layer is deliberately split into:

```text
Domain entities/value objects
          ↓ adapter mapping
SQLAlchemy metadata (development mapping)
          ↓
Frozen Alembic SQL snapshot (historical migration truth)
          ↓
PostgreSQL 17 + pgvector
```

Historical migrations never import current SQLAlchemy models. A revision executes its own immutable SQL snapshot so replaying old migrations in the future cannot silently change because the current ORM evolved.

## 2. Database baseline

Local/CI infrastructure baseline:

```text
PostgreSQL 17
pgvector extension 0.8.6 image baseline
pgcrypto extension
application role: lumi_app
migration role: lumi_migration
local superuser: lumi_admin
```

The NODE-10 validation workflow installs exact migration-tool versions transiently:

```text
SQLAlchemy 2.0.51
Alembic 1.18.5
asyncpg 0.31.0
```

These packages are intentionally not added to the workspace lock in NODE-10. The persistence implementation is isolated behind imports with CI-safe missing-import type suppressions while the existing repository lock remains frozen. NODE-11, which integrates the database into the application/API runtime, is the point where runtime dependencies must be added to `apps/api/pyproject.toml` and `uv.lock` together.

This boundary avoids weakening the existing frozen-install gate merely to make a technology/persistence node pass.

## 3. P0 table inventory

NODE-10 creates **40 P0 tables**.

### Identity & tenancy

```text
users
organizations
organization_members
workspaces
workspace_members
auth_identities
```

### Brand / project

```text
brands
brand_palettes
brand_fonts
brand_logos
brand_rules
projects
project_members
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

### Design / artifact / version

```text
design_documents
design_document_versions
artifacts
artifact_branches
artifact_versions
artifact_edges
artifact_files
artifact_provenance
```

### Agent / task / generation

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

### Billing / events / governance

```text
cost_ledger
usage_counters
outbox_events
inbox_events
audit_events
```

## 4. Tenant model

Thirty-seven tables are tenant-owned and have a mandatory non-null `organization_id`.

The only P0 tables without `organization_id` are:

```text
users
organizations
auth_identities
```

Reason:

- `organizations.id` is the tenant identity itself;
- a user/auth identity may belong to multiple organizations;
- membership rows connect global identity to tenant scope.

### Defense in depth

Tenant isolation has three layers:

1. **Application authorization** — NODE-11 must verify user membership/role before opening a tenant session.
2. **Session tenant context** — `tenant_session()` sets transaction-local `app.current_organization_id`.
3. **PostgreSQL RLS** — all 37 tenant tables have `USING` + `WITH CHECK` policies matching that setting.

RLS is defense in depth, not a replacement for membership authorization.

## 5. Cross-tenant foreign-reference protection

A row can have a correct `organization_id` yet still point to another tenant's project, asset, branch or task. Ordinary single-column foreign keys cannot prevent that.

The P0 migration therefore installs `lumi_enforce_same_tenant_fk()` and relationship-specific triggers across tenant-owned references.

Important security detail:

```text
SECURITY DEFINER
SET search_path = public, pg_temp
```

is intentional. An invoker-rights trigger would itself be filtered by RLS and could fail to see a referenced row owned by another tenant. The narrowly scoped definer function can inspect the referenced row's real `organization_id`, while the fixed search path prevents object-shadowing attacks.

Design-document `head_version_id` and version `parent_version_id` are explicitly covered, not only their project/document roots.

## 6. IDs

All application-owned primary keys are UUIDs supplied by the application/domain layer. NODE-09 generates UUIDv7-compatible IDs.

Rules:

- no public autoincrement business IDs;
- provider-native IDs remain separate (`provider_requests.provider_request_id`);
- idempotency identity remains separate from provider identity;
- UUID timestamp ordering is not authorization or causal ordering.

## 7. Exact numeric persistence

Money and billable usage never use `FLOAT`, `REAL` or `DOUBLE PRECISION`.

Key fields:

```text
agent_runs.budget_amount      NUMERIC(20,8)
tasks.budget_reserved         NUMERIC(20,8)
cost_ledger.amount            NUMERIC(20,8)
cost_ledger.quantity          NUMERIC(30,10)
usage_counters.quantity       NUMERIC(30,10)
artifact_versions.quality_score NUMERIC(8,5)
```

The deterministic validator fails if any SQLAlchemy column is `Float` or the frozen SQL snapshot contains floating-point SQL types.

## 8. Optimistic concurrency

Mutable aggregate tables carry:

```text
created_at timestamptz
updated_at timestamptz
version integer >= 1
```

The expected write pattern is:

```sql
UPDATE projects
SET ..., version = version + 1
WHERE id = :id
  AND organization_id = :organization_id
  AND version = :expected_version;
```

`UPDATE 0` means stale state or inaccessible row; the application service must surface a concurrency conflict instead of blindly overwriting another edit.

`updated_at` is enforced by PostgreSQL triggers, not only ORM conventions.

## 9. Soft delete vs immutable history

Soft delete is reserved for mutable top-level entities where recovery/history is useful:

```text
brands
projects
assets
design_documents
artifacts
```

Immutable/history tables are not soft-deleted.

### Fully immutable row history

Database triggers reject `UPDATE` and `DELETE` on:

```text
cost_ledger
audit_events
inbox_events
design_document_versions
artifact_provenance
```

### ArtifactVersion rule

Artifact versions may move through their approval state machine before approval. Once `OLD.status = 'approved'`, further mutation is rejected. Artifact-version deletes are always rejected.

A correction creates a new version rather than changing approved history.

## 10. Cost ledger

`cost_ledger` is append-only.

```text
charge      → related_entry_id must be NULL
reversal    → related_entry_id required
adjustment  → related_entry_id required
```

Provider/project/task/run/generation references are preserved when available. Amount and quantity use exact numeric types.

Application role `lumi_app` has `UPDATE`/`DELETE` revoked on the ledger in addition to the immutable trigger.

## 11. Idempotency

Paid/external side effects use `idempotency_operations` with:

```text
UNIQUE (organization_id, idempotency_key)
request_hash
operation_type
status
response_json
expires_at
```

`generations.operation_id` references the idempotency record. Retrying the same tenant/key cannot silently create a second paid operation.

Provider request identity is intentionally separate because one domain operation may retry or route across provider calls.

## 12. Task DAG

`task_dependencies(task_id, depends_on_task_id)` has:

- composite primary key;
- no self-dependency check;
- same-tenant reference trigger;
- recursive cycle-rejection trigger;
- reverse lookup index on `depends_on_task_id`.

The domain layer still validates the DAG before persistence; the database trigger protects against bypass/races and manual writes.

## 13. Artifact lineage

`artifact_edges` stores provenance relationships:

```text
DERIVED_FROM
EDITED_FROM
COMPOSED_FROM
RESIZED_FROM
EXPORTED_FROM
GENERATED_FROM_ASSET
```

It rejects:

- self-edges;
- duplicate typed edges;
- cross-tenant endpoints;
- recursive lineage cycles.

`artifact_provenance` stores immutable provenance payload/hash data separately from the graph edge itself.

## 14. Design document versioning

```text
design_documents
  └─ head_version_id

design_document_versions
  ├─ version_number
  ├─ parent_version_id
  ├─ content_json
  └─ content_hash
```

Version rows are immutable. The mutable document root points at a version. This avoids editing historical JSON in place and gives later Design IR migrations a clear version boundary.

## 15. pgvector strategy

`asset_embeddings.embedding` uses PostgreSQL `vector` but does **not** freeze a dimension in NODE-10.

Reason: the production embedding model/dimension is not yet a frozen routing contract. The row stores:

```text
embedding_model
embedding_version
dimensions
content_hash
embedding vector
```

When NODE-23/knowledge/model routing freezes a production embedding dimension, a later migration can add dimension-specific tables/indexes or constraints without invalidating the P0 schema.

The schema layer uses a small SQLAlchemy `VectorType` so migration metadata is not coupled to the pgvector Python runtime package. Runtime codecs can be added at the application adapter boundary later.

## 16. JSONB boundaries

JSONB is used for evolving payloads whose inner schema belongs to another contract/versioned representation, including:

```text
project brief/settings
brand profile/rules/palette
asset semantic metadata
Design IR version content
agent usage/trace refs
provider request/response
outbox payload
provenance payload
```

Core identity, status, ownership, cost, ordering, FK and lifecycle fields remain typed columns rather than opaque JSON.

## 17. Outbox / Inbox

`outbox_events` enables domain mutation + event recording in the same PostgreSQL transaction.

`inbox_events(event_id, consumer)` provides consumer deduplication and is immutable after processing.

The NODE-10 PostgreSQL integration test deliberately inserts a project + outbox event in one transaction, raises an error, and verifies both rolled back.

Actual broker publishing/consumer orchestration belongs to NODE-12.

## 18. Audit chain groundwork

`audit_events` is immutable and includes:

```text
actor_type / actor_id
action
subject_type / subject_id
details_json
previous_hash
event_hash
```

Hash-chain production/verification logic belongs to the governance/audit implementation nodes. NODE-10 only provides an immutable persistence shape.

## 19. Database roles

### `lumi_migration`

Owns schema migration operations. It can bypass ordinary application RLS by virtue of schema ownership where PostgreSQL ownership semantics apply. It must not be used by normal API requests.

### `lumi_app`

Runtime application role. It is subject to RLS and receives normal DML grants, with mutation privileges revoked for immutable history tables where appropriate.

### `lumi_admin`

Local infrastructure/bootstrap administration role only. Production credential management is outside this local fixture contract.

## 20. Migration strategy

First revision:

```text
revision = 20260816_0001
```

The revision reads only:

```text
20260816_0001_sql/up_01.sql ... up_08.sql
20260816_0001_sql/down_01.sql ... down_02.sql
```

It does **not** import `Base.metadata` or current ORM models.

Migration acceptance requires:

```text
upgrade head
seed
integration invariants
downgrade base
verify P0 schema removed
upgrade head again
seed again
integration invariants again
```

This tests both rollback and deterministic reapplication.

## 21. Deterministic seed

`apps/api/migrations/seeds/p0_local_fixture.sql` contains two tenants with stable UUIDv7-shaped IDs and representative:

- users/memberships/workspaces;
- brands/projects;
- assets/storage checksum data;
- task dependency;
- DesignDocument/version;
- Artifact/branch/version;
- idempotency operation;
- generation;
- exact Cost Ledger entry.

It is a local/CI fixture, not production seed data.

## 22. Validation

Static deterministic validator:

```bash
PYTHONPATH=apps/api/src python tools/node10/validate_schema.py
```

It checks:

- exact 40-table metadata/snapshot inventory;
- 37 mandatory tenant scopes;
- 37 RLS enable statements and 37 policies;
- exact numeric persistence;
- PostgreSQL SQLAlchemy metadata compilation;
- pgvector/pgcrypto extensions;
- frozen revision isolation;
- immutable history triggers;
- task/artifact cycle guards;
- RLS-safe same-tenant reference guard;
- design head/parent tenant protection;
- idempotency/outbox/inbox safeguards.

PostgreSQL integration test:

```bash
python tools/node10/test_database_integration.py
```

It validates nine groups:

1. Alembic revision applied;
2. tenant A/B RLS visibility;
3. cross-tenant FK/reference rejection;
4. optimistic concurrency stale-write behavior;
5. exact Decimal money and duplicate idempotency rejection;
6. task DAG cycle rejection;
7. artifact lineage cycle rejection;
8. approved version + ledger immutability;
9. project/outbox atomic rollback.

## 23. Known limitations / deferred work

NODE-10 intentionally does not claim:

- API membership authorization implementation — NODE-11;
- a production connection pool size for every deployment — environment configurable;
- production embedding index/dimension — later retrieval/model-routing contract;
- event broker delivery — NODE-12;
- full audit hash-chain writer/verifier — later governance node;
- database backup/PITR/HA — deployment/operations nodes;
- final production PostgreSQL service credentials — deployment secrets work;
- a complete persistence repository implementation for every aggregate — NODE-11/application adapters.

## 24. Definition of Done

NODE-10 becomes COMPLETE only when:

```text
40-table persistence mapping
+ frozen Alembic revision
+ seed fixture
+ RLS and same-tenant guards
+ exact money
+ optimistic concurrency
+ DAG/lineage guards
+ immutable ledger/version history
+ idempotency/outbox
+ upgrade/downgrade/reapply tests
+ repository CI/security green
+ stacked dependency NODE-09 resolved
+ merged to main
```

Until then it remains `VALIDATING` or `BLOCKED_EXTERNAL / VALIDATING` as evidence dictates.

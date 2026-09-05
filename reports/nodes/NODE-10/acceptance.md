# NODE-10 Acceptance Report

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Node: **NODE-10 — Database Schema**  
> Branch: `node-10-database-schema`  
> Stack base: `node-09-domain-model`  
> Database target: PostgreSQL 16 + pgvector  
> Persistence: SQLAlchemy 2 async + asyncpg + Alembic

---

## 1. Acceptance result so far

NODE-10 has implemented the persistence architecture, 41-table P0 schema, frozen migration chain, tenant-scoped repository foundation, deterministic seed, static schema contracts and a dedicated live PostgreSQL validation workflow.

It is **not COMPLETE** because two external/reproducibility gates are intentionally unresolved:

1. GitHub Actions cannot currently start hosted runners because the repository/account billing or Actions spending limit requires attention.
2. New Python dependencies were added to `apps/api/pyproject.toml`, therefore the existing `uv.lock` is intentionally stale until a real dependency resolution can run. The lock file has not been hand-edited.

The correct state is therefore `IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`.

## 2. External GitHub Actions blocker

GitHub check annotations have already diagnosed the failure precisely:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased.
Please check the 'Billing & plans' section in your settings.
```

Observed failed checks have:

```text
runner_id = 0
runner_name = ""
steps = []
```

No checkout, dependency install, lint, typecheck, test or migration step executes in those runs. They are not counted as product test failures or passes.

Required external action:

```text
GitHub Settings
→ Billing & plans
→ resolve failed payment and/or increase Actions spending limit
```

Repeated workflow reruns are intentionally avoided until that condition is fixed.

## 3. Dependency-lock boundary

NODE-10 declares new runtime dependencies:

```text
SQLAlchemy[asyncio] 2.0.51
Alembic 1.18.5
asyncpg 0.31.0
pgvector 0.5.0
lumi-domain workspace package
```

Because dependency resolution is not currently being executed in a trusted reproducible environment, `uv.lock` has **not** been manually synthesized or edited.

Expected first validation after Actions/billing recovery:

```text
uv lock
uv sync --all-packages --frozen
```

The resulting lock diff must be reviewed and committed before NODE-10 can pass its frozen-install gate.

## 4. Implemented persistence foundation

### Configuration

Runtime and migration connections are separated:

```text
DATABASE_URL           = postgresql+asyncpg://lumi_app:...
MIGRATION_DATABASE_URL = postgresql+asyncpg://lumi_migration:...
```

`session.py` rejects non-asyncpg runtime URLs.

### SQLAlchemy foundation

Implemented:

```text
DeclarativeBase
application UUIDv7 IdMixin
created_at mixin
mutable updated_at/version mixin
async engine
async_sessionmaker
transactional session_scope
```

Domain entities are not SQLAlchemy models.

## 5. P0 schema inventory

Exactly **41** ORM application tables are registered.

| Context | Table count |
|---|---:|
| Identity & Tenancy | 7 |
| Project & Brand | 7 |
| Asset | 6 |
| Design / Artifact / Provenance | 8 |
| Agent / Workflow / Generation | 7 |
| Platform | 6 |
| **Total** | **41** |

Full table inventory is documented in `docs/database/DATABASE-SCHEMA.md`.

## 6. Tenant isolation implementation

Tenant-owned tables carry direct `organization_id` ownership.

`TenantRepository` applies:

```text
WHERE model.organization_id = repository.organization_id
```

`ProjectRepositoryAdapter` additionally rejects saving a domain Project whose organization does not match the repository tenant.

The live test suite contains a cross-tenant fixture proving an organization-A repository cannot retrieve an organization-B project once PostgreSQL validation can run.

## 7. UUID strategy

ORM `id` columns use application-generated NODE-09 UUIDv7 values.

Static schema tests assert business ID columns have no server UUID default.

Provider-native request IDs remain separate fields.

## 8. Mutable / immutable data enforcement

### Immutable history

Final migration head installs PostgreSQL triggers rejecting UPDATE/DELETE on:

```text
design_document_versions
artifact_edges
artifact_files
artifact_provenance
cost_ledger
inbox_events
audit_events
```

`lumi_app` also receives only SELECT/INSERT on those tables.

### ArtifactVersion controlled mutation

Runtime may:

```text
INSERT artifact_versions
UPDATE artifact_versions(status, quality_score)
```

but does not get broad content UPDATE/DELETE permission.

### Soft delete

Only:

```text
projects
assets
```

carry P0 `deleted_at` fields.

## 9. Precision contract

Financial and billable values use Decimal-compatible PostgreSQL NUMERIC:

```text
cost_ledger.amount      NUMERIC(20,8)
cost_ledger.quantity    NUMERIC(30,10)
usage_counters.quantity NUMERIC(30,10)
tasks.budget_reserved   NUMERIC(20,8)
```

`cost_ledger.currency` is `CHAR(3)` with uppercase-three-letter CHECK.

Static and live tests cover the precision contract.

## 10. Artifact and task graph safety

Database guards:

```text
artifact_edges: no self-loop + unique directed typed edge
task_dependencies: no self-loop + unique dependency edge
```

Full cycle detection remains a NODE-09 domain/service responsibility rather than a database graph trigger.

## 11. Asset / vector strategy

Asset storage is normalized:

```text
Asset identity
→ AssetFile variant
→ bucket/object_key
→ sha256/mime/byte_size/dimensions
```

Rights are separate in `asset_rights`.

Embeddings record:

```text
embedding_model
embedding_version
content_hash
dimensions
vector
```

No global vector dimension or ANN index is invented before a benchmarked embedding model is frozen.

## 12. Repository / concurrency contract

Implemented `ProjectRepositoryAdapter.save_with_expected_version()` uses tenant + expected version optimistic locking.

Conceptual SQL:

```text
UPDATE projects
SET ..., version = version + 1
WHERE id = :id
  AND organization_id = :tenant
  AND version = :expected
  AND deleted_at IS NULL
RETURNING version
```

No row -> `OptimisticLockError`.

## 13. Idempotency and provider persistence

Implemented:

```text
idempotency_operations
UNIQUE (organization_id, idempotency_key)

generations.operation_id
→ idempotency_operations.id

provider_requests
→ provider native request ID
→ normalized error_code/error_retryable
→ usage_json/latency
```

This provides the durable basis for NODE-20 side-effect reconciliation.

## 14. Cost ledger contract

`cost_ledger` is append-only and has no `updated_at`.

Corrections use new rows via `reverses_entry_id`.

A live PostgreSQL acceptance test intentionally attempts UPDATE and expects a DB-level error from the immutable trigger.

## 15. Transactional Outbox / Inbox

`append_outbox_event()` uses the caller's current `AsyncSession`, allowing business mutation and event insertion in the same transaction.

Live acceptance test:

```text
insert Project
insert OutboxEvent
ROLLBACK
→ Project absent
→ OutboxEvent absent
```

Inbox dedupe is enforced by:

```text
UNIQUE (consumer, event_id)
```

## 16. Alembic migration chain

Frozen revisions:

```text
0001_domain_core_schema
→ 0002_workflow_platform_schema
→ 0003_runtime_privilege_hardening
```

Properties:

- historical revisions contain static schema DDL;
- no `Base.metadata.create_all()`;
- migration role is distinct from runtime role;
- head revokes broad runtime writes and applies explicit least privilege;
- immutable-history triggers are installed at head;
- structural drift is checked using `alembic check`.

## 17. Deterministic seed

`lumi_api.persistence.seed` provides repeatable fixed-ID fixtures:

```text
2 users
1 org + membership
1 workspace
1 brand
2 projects
1 asset + file + rights
1 design document
1 artifact branch
2 artifact versions + lineage edge
2 tasks + dependency
```

Seed writes use `ON CONFLICT DO NOTHING` to remain rerunnable.

## 18. Static acceptance tests implemented

`apps/api/tests/test_persistence_schema.py` verifies:

- exact 41-table set;
- tenant column presence;
- no database-generated domain UUID defaults;
- soft-delete policy;
- immutable-history timestamp policy;
- NUMERIC precision;
- compiled tenant predicate;
- asyncpg runtime URL requirement;
- frozen migration chain;
- no `metadata.create_all()` shortcut;
- immutable trigger/granular privilege DDL;
- artifact/task self-loop checks.

These tests are implemented but have not yet received a real Python 3.12 CI execution because of the known Actions billing blocker and stale lock.

## 19. Live PostgreSQL acceptance tests implemented

`apps/api/tests/integration/test_database_persistence.py` is opt-in via:

```text
LUMI_DB_INTEGRATION=1
```

It tests:

1. head revision = `0003_runtime_privilege_hardening`;
2. 41 application tables exist;
3. cross-tenant Project isolation;
4. optimistic-lock success + stale conflict;
5. Decimal precision round-trip;
6. immutable CostLedger rejects UPDATE;
7. Project + Outbox rollback atomicity.

The tests are deliberately transactional/rollback-oriented where possible so repeated execution does not pollute the database.

## 20. Dedicated Database Schema Gate

`.github/workflows/database-schema.yml` is implemented and will run after Actions recovery:

```text
Frozen Python install
→ local infrastructure
→ empty DB upgrade to head
→ alembic check
→ deterministic seed
→ current revision check
→ downgrade -1 / upgrade head
→ alembic check
→ live PostgreSQL tests
→ cleanup
```

## 21. Acceptance matrix

| Requirement | Implementation | Real validation |
|---|---|---|
| PostgreSQL schema | IMPLEMENTED | BLOCKED_EXTERNAL |
| SQLAlchemy async models | IMPLEMENTED | BLOCKED_EXTERNAL |
| Alembic migrations | IMPLEMENTED | BLOCKED_EXTERNAL |
| Runtime/migration role split | IMPLEMENTED | prior infra role exists; NODE-10 migration validation blocked |
| 41-table P0 model | IMPLEMENTED | static test written; not executed on current head |
| UUIDv7 application IDs | IMPLEMENTED | NODE-09 semantics + schema contract written |
| tenant scoping | IMPLEMENTED | live isolation test written |
| optimistic locking | IMPLEMENTED | live test written |
| append-only cost/audit/history | IMPLEMENTED | DB triggers + live mutation test written |
| money precision | IMPLEMENTED | static/live tests written |
| Outbox/Inbox | IMPLEMENTED | atomicity/dedupe tests written |
| pgvector storage | IMPLEMENTED | live extension/schema validation blocked |
| deterministic seed | IMPLEMENTED | live seed execution blocked |
| migration downgrade smoke | IMPLEMENTED | real execution blocked |
| Alembic schema drift gate | IMPLEMENTED | real execution blocked |
| Ruff/Pyright/Pytest | tests/config ready | BLOCKED_EXTERNAL |
| frozen `uv.lock` | **NOT UPDATED** | requires real dependency resolution |

## 22. Completion gate

NODE-10 may be marked `COMPLETE` only after all of the following occur:

```text
GitHub Billing & plans / Actions spending fixed
+ real uv lock generated and committed
+ uv sync --all-packages --frozen PASS
+ Ruff format PASS
+ Ruff lint PASS
+ Pyright PASS
+ Pytest PASS
+ Database Schema workflow PASS
+ Alembic check PASS
+ existing contracts/eval/security gates PASS
```

Until then:

**NODE-10 engineering status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL.**

Engineering may continue through stacked branches, but NODE-11 cannot be labeled complete until dependency order is restored and validated.

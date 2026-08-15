# NODE-10 — Acceptance Evidence

> Status: **VALIDATING**  
> Branch: `feat/node-10-database-schema`  
> Stacked Base: `feat/node-09-domain-model` / PR #75  
> Node: Database Schema  
> Date: 2026-08-16

## Scope implemented

NODE-10 translates NODE-09 into PostgreSQL persistence without redefining domain semantics.

Implemented:

- 40-table SQLAlchemy P0 metadata split by bounded-context-oriented modules;
- 37 tenant-owned tables with mandatory non-null `organization_id`;
- UUID application-owned primary keys;
- mutable timestamps/version columns and database-side `updated_at` triggers;
- soft-delete only on selected recoverable top-level entities;
- exact NUMERIC money/usage fields;
- PostgreSQL `vector` asset-embedding boundary without fabricating a production dimension;
- Project/Asset/Design/Artifact/Agent/Task/Generation/Cost/Event persistence;
- tenant-scoped idempotency operations;
- append-only Cost Ledger semantics;
- Outbox/Inbox persistence;
- immutable audit/version/provenance history safeguards;
- Task DAG and Artifact lineage recursive cycle rejection;
- RLS on every tenant table;
- RLS-safe cross-tenant reference protection using a constrained SECURITY DEFINER trigger function;
- async tenant-session boundary;
- frozen Alembic SQL snapshot and rollback snapshot;
- deterministic two-tenant seed;
- static schema contract validator;
- real asyncpg PostgreSQL invariant suite;
- dedicated upgrade/seed/test/downgrade/reapply/test GitHub Actions gate.

Canonical documentation:

```text
docs/database/SCHEMA.md
```

## Local deterministic validation

Evidence:

```text
reports/nodes/NODE-10/local-schema-validation.txt
```

Available fallback environment:

```text
Python 3.13.5
SQLAlchemy 2.0.50
Docker/PostgreSQL unavailable
```

Observed:

```text
LOCAL_SCHEMA_VALIDATION_PASS 40 37 94
COMPILEALL_PASS
```

Meaning:

- 40 P0 tables accounted for;
- 37 tenant table organization columns accounted for;
- 37 RLS enable statements + 37 policies present;
- SQLAlchemy metadata compiled through PostgreSQL mock dialect;
- no persistence Float accepted;
- exact Numeric ledger/budget fields present;
- frozen migration includes pgvector/pgcrypto, immutable-history triggers, tenant guards, cycle guards, idempotency and Outbox/Inbox;
- tenant-reference guard uses `SECURITY DEFINER SET search_path = public, pg_temp`;
- DesignDocument head/parent references are tenant-checked;
- persistence Python package compiles.

This evidence is supplementary. It does **not** claim that PostgreSQL/Alembic/asyncpg dynamic behavior passed because the fallback container has no Docker/PostgreSQL runtime.

## Frozen migration contract

Revision:

```text
20260816_0001
```

The revision executes only its own SQL files:

```text
20260816_0001_sql/up_01.sql ... up_08.sql
20260816_0001_sql/down_01.sql ... down_02.sql
```

The validator rejects current ORM imports in that revision. Historical migration replay therefore cannot silently change when later ORM mappings evolve.

## Tenant isolation evidence design

The dedicated PostgreSQL suite validates both read and write isolation:

1. set tenant A context and require only tenant A projects visible;
2. set tenant B context and require only tenant B projects visible;
3. attempt to create a tenant B project that references tenant A workspace and require SQLSTATE `23514` rejection.

The third case is important because row-level RLS alone cannot prove referenced rows belong to the same tenant.

During implementation, an invoker-rights version of the same-tenant trigger was identified as unsafe: RLS could hide the foreign tenant's referenced row from the trigger itself. The migration was corrected to use a migration-owned SECURITY DEFINER function with fixed `search_path = public, pg_temp` and the static validator now asserts that safeguard.

## Dynamic integration suite

`tools/node10/test_database_integration.py` contains nine PostgreSQL invariant groups:

```text
1. Alembic revision = 20260816_0001
2. RLS tenant A/B cross-read isolation
3. cross-tenant relationship write rejection
4. optimistic stale-write rejection (UPDATE 0)
5. exact Decimal money + duplicate idempotency rejection
6. Task DAG recursive cycle rejection
7. Artifact lineage recursive cycle rejection
8. approved ArtifactVersion + Cost Ledger immutability
9. Project + Outbox transaction atomic rollback
```

The dedicated workflow runs the suite once after first migration and again after full `downgrade base → upgrade head` reapplication.

## Runtime dependency boundary

NODE-10 does not modify the existing frozen workspace lock. The dedicated database workflow installs exact migration/test packages transiently:

```text
SQLAlchemy 2.0.51
Alembic 1.18.5
asyncpg 0.31.0
```

NODE-11 must add the selected runtime database dependencies to `apps/api/pyproject.toml` and `uv.lock` together when the API/application layer begins importing persistence adapters at runtime. NODE-10 does not disable or weaken the repository `uv sync --frozen` gate.

## GitHub Actions evidence

Pending NODE-10 pull request creation and first workflow execution.

The repository currently has an account-level GitHub Actions payment/spending-limit block independently recorded by NODE-08 and NODE-09. NODE-10 will record its own run/job evidence after opening its stacked PR and will not inherit or assume the result.

## Acceptance checklist

- [x] 40 P0 tables mapped.
- [x] 37 tenant tables require organization_id.
- [x] 37 RLS policies frozen in migration.
- [x] cross-tenant references protected by RLS-safe tenant guard.
- [x] exact NUMERIC money/usage; Float forbidden by validator.
- [x] optimistic concurrency version fields/pattern frozen.
- [x] Task DAG and Artifact lineage cycle rejection implemented.
- [x] Cost Ledger immutable/reversal-adjustment semantics implemented.
- [x] approved ArtifactVersion immutability implemented.
- [x] idempotency operation uniqueness implemented.
- [x] Outbox/Inbox implemented.
- [x] deterministic two-tenant seed implemented.
- [x] frozen upgrade/downgrade snapshots implemented.
- [x] local static schema validation passes.
- [ ] empty PostgreSQL `upgrade head` passes.
- [ ] two-tenant RLS integration passes.
- [ ] cross-tenant relationship write rejection passes.
- [ ] optimistic concurrency/Decimal/idempotency integration passes.
- [ ] Task/Artifact cycle integration passes.
- [ ] immutable-history integration passes.
- [ ] Outbox atomic rollback integration passes.
- [ ] downgrade base removes P0 schema.
- [ ] reapply + reseed + second integration pass succeeds.
- [ ] repository CI/security gates pass.
- [ ] NODE-09 dependency resolves and stacked PR merges.
- [ ] NODE index updated to COMPLETE.

NODE-10 remains `VALIDATING`, not `COMPLETE`.

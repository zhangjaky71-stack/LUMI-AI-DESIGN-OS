# NODE-42 Acceptance — Artifact Engine Runtime

## Status

`IMPLEMENTED / VALIDATING`

Hosted GitHub Actions PASS is not claimed until the dedicated workflow executes on an allocated runner.

## Delivered

- NODE-15 canonical Artifact/Version/Branch/File/Lineage/Provenance contracts retained;
- transactional Artifact Engine service and repository port;
- deterministic in-memory transactional twin for P0 concurrency/rollback tests;
- PostgreSQL repository with tenant scoping and branch-row `FOR UPDATE` compare-and-swap;
- Artifact + main + optional v1 atomic creation;
- immutable version append, fork, restore-as-new-version, multi-parent lineage;
- READY/APPROVED status transitions with exact immutable approval record;
- storage existence/checksum/size/MIME/tenant verification before file attach;
- storage blob reuse across immutable versions without cross-tenant authorization sharing;
- provenance completeness scoring and queryable provenance identity fields;
- NODE-38 semantic-diff adapter and raster visual-diff port;
- two-stage GC mark/recheck/delete + audit;
- transactional artifact outbox persistence;
- forward migration `20260817_0011` closing the major NODE-15 persistence-shape gaps;
- authenticated v1 Artifact API facade and organization scoping;
- P0 pytest suite, runtime smoke, static validator, dedicated CI and five-gap production ledger.

## Local evidence

Observed against the exact local NODE-42 candidate in the isolated environment:

```text
7 passed in 0.21s
NODE42_ARTIFACT_ENGINE_RUNTIME_SMOKE_PASS
versions=4 lineage=6 outbox=8 gc_audits=2
NODE42_PYTHON_COMPILEALL_PASS
```

The P0 suite covers optional-v1 atomic creation, concurrent branch-head CAS, fork/restore, multi-parent lineage, approved immutability, storage rejection, cross-tenant equal-hash isolation, and live-reference GC protection.

No live PostgreSQL service, repository-pinned Python 3.12/uv environment, Ruff, Pyright, or hosted CI execution is claimed locally.

## Database qualification

The migration preserves existing lowercase database status values and adds `archived`. It migrates `GENERATED_FROM_ASSET` to canonical `GENERATED_FROM`, adds `REFERENCE_USED`, removes the old global ArtifactFile object-location unique constraint, and adds version-scoped uniqueness.

Downgrade fails closed when data uses semantics that the old schema cannot represent safely.

The PostgreSQL repository uses an organization-scoped dedicated SQLAlchemy Session and owns short write transactions. Version append locks the branch row and writes version/files/provenance/lineage/head/outbox in one transaction.

A real PostgreSQL upgrade/downgrade + concurrent writer test remains a production acceptance gap and is not inferred from static SQL inspection.

## Production gaps

Exactly five are tracked:

1. production S3/R2 authorized stat/list/delete adapter;
2. live PostgreSQL migration/concurrency/load acceptance;
3. production design-document reader + raster visual-diff adapter;
4. durable transactional-outbox relay worker;
5. scheduled retention/legal-hold purge + GC operations/observability.

See `reports/nodes/NODE-42/gap-ledger.json`.

## Hosted acceptance gate

Before NODE-42 can be COMPLETE, an allocated runner must execute frozen Python workspace installation, P0 tests, static validation, Ruff, Pyright, migration snapshot checks, and repository-wide relevant gates. Infrastructure-specific gaps then require their own real-service evidence.

Next node: **NODE-43 — Brand Rules Engine**.

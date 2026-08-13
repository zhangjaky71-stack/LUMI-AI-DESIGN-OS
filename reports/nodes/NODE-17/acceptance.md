# NODE-17 Acceptance — Project Core

> Status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL  
> Date: 2026-08-13  
> Branch: `node-17-project-core`

## Scope implemented

- [x] Project/Brief/Settings V1 machine contracts.
- [x] Project status aligned to existing domain/API/database values.
- [x] Structured Brief contains objective, audience, brand context, deliverables, channels, visual direction, copy requirements, constraint refs, asset refs, locale and notes.
- [x] Canonical UTF-8 Brief hash.
- [x] Immutable `project_brief_versions` history table and DB mutation-rejection trigger.
- [x] `projects.brief_version` current pointer.
- [x] Rebuildable `project_summaries` projection.
- [x] Strict Project settings allowlist; secrets excluded.
- [x] Transactional Project create with idempotency + Brief v1 + Summary + Outbox + Audit.
- [x] Tenant-scoped Project get/list/update/archive/restore.
- [x] Optimistic concurrency / `If-Match` contract.
- [x] Material Brief changes only create new Brief versions.
- [x] Archive preserves assets/history.
- [x] Explicit restore semantics: `archived -> paused`.
- [x] Paid-command guard requires `active` and not deleted.
- [x] List filters and deterministic opaque cursor.
- [x] Project Brief history API.
- [x] Authenticated Project runtime using NODE-16 Session/API Token principals.
- [x] Browser CSRF enforcement on Project mutations.
- [x] Cross-tenant Session/API Token authorization boundary.
- [x] Project Core Gateway explicitly leaves non-NODE-17 operations unimplemented.
- [x] Deterministic seed corrected to frozen NODE-16 roles and NODE-17 Project contracts.
- [x] Dependency-free Project Contract workflow.
- [x] PostgreSQL/Auth Project Integration workflow.
- [x] Project Core implementation document.

## Contract validation prepared

The following checks are committed but are **not recorded as PASS** until a runner actually executes them:

```text
python -m compileall -q services/project-core/src scripts/validate_project_contracts.py
python scripts/validate_project_contracts.py
python -m unittest discover -s services/project-core/tests -p 'test_*.py' -v
```

They cover:

- Draft 2020-12 schema IDs;
- strict Brief fields;
- strict Settings fields;
- canonical lowercase Project statuses;
- no heavy runtime dependencies in `lumi-project-core`;
- NODE-17 migration chain;
- immutable Brief history trigger;
- Unicode canonical hash;
- settings secret rejection;
- restore/paid-command lifecycle;
- cursor and filter behavior.

## Full integration validation prepared

`Project Integration` is configured to run:

```text
uv sync --all-packages --frozen
ruff
pyright
PostgreSQL
Alembic upgrade to 0006_project_core
ORM/migration drift check
seed
persistence schema test
Project Core DB integration
Project Auth/Tenant/CSRF integration
```

The integration suite checks:

- Project create transaction atomicity;
- idempotent retry and payload mismatch rejection;
- Brief version append behavior;
- stale optimistic version rejection;
- archive prevents paid commands;
- restore returns paused and still prevents paid commands;
- archive does not delete project assets;
- cross-tenant Project lookup rejection;
- cursor pages do not duplicate Projects;
- PostgreSQL rejects UPDATE of Brief history;
- tenant header alone does not authenticate;
- authenticated Session read works;
- cross-tenant Session is rejected;
- browser mutation without CSRF is rejected;
- VIEWER can read but cannot write.

## Database acceptance target

Expected current database after NODE-17:

```text
Alembic head: 0006_project_core
Business tables: 48
```

New tables:

```text
project_brief_versions
project_summaries
```

## Known blockers

### 1. GitHub Actions hosted runners

Hosted jobs cannot currently start because the GitHub account requires billing/Actions spending attention. This is external to the source changes.

**No CI job is marked PASS in this report.**

### 2. Python lock

`uv.lock` remains intentionally stale. It has not been hand-edited. It must be regenerated from the real workspace after external execution is available; the new `lumi-project-core` workspace member must be resolved by `uv lock`.

## Completion gate

NODE-17 may move from `IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL` to `COMPLETE` only after:

1. real `uv lock` regeneration and commit;
2. `uv sync --all-packages --frozen` PASS;
3. `Project Contract` PASS;
4. global Python format/lint/type/test gates remain green;
5. empty PostgreSQL -> `0006_project_core` PASS;
6. ORM/migration drift check PASS;
7. deterministic seed PASS;
8. Project Integration DB tests PASS;
9. Project Auth/Tenant/CSRF tests PASS;
10. evidence is recorded here.

## Downstream readiness

Engineering may continue through stacked NODE-18 while external validation is blocked, because NODE-17 contracts are implemented and versioned. NODE-18 must consume Project tenant/project scope and must not reinterpret archive as physical asset deletion.

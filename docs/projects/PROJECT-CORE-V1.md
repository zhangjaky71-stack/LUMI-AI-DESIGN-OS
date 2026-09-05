# LUMI Project Core V1

> Node: NODE-17  
> Phase: 2 Runtime Foundation  
> Status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL  
> Contract: `contracts/projects/v1/`

## 1. Purpose

Project is the durable business scope for LUMI design work. A chat thread, LangGraph thread, AgentRun or generation request is never the project truth by itself. Assets, artifacts, tasks, agent runs, cost and future design runtime operations must resolve through a tenant-scoped Project.

## 2. Canonical Project state

Persistent Project status uses the existing domain/API/database values:

```text
draft
active
paused
archived
```

Normal domain transitions remain owned by `lumi_domain.ProjectStatus`.

NODE-17 adds one explicit recovery command:

```text
archived --restore--> paused
```

Restore deliberately returns `paused`, not `active`. Recovery must never silently re-enable paid generation. A user or authorized service must explicitly activate the Project after review.

## 3. Structured Brief V1

`project-brief.schema.json` freezes:

```text
schema_version
objective
audience
brand_context
deliverables
channels
visual_direction
copy_requirements
constraint_ids
reference_asset_ids
locale
notes
```

`constraint_ids` reference NODE-14 structured constraints. Constraint bodies are not copied into `brief_json`.

`reference_asset_ids` reference asset records. Binary files are not embedded in the Brief.

The raw user prompt may be retained as controlled `source_input` on a Brief history record, but downstream Agents should primarily consume the structured Brief.

## 4. Brief versioning

`projects.brief_json` is the current materialized Brief and `projects.brief_version` identifies its current version.

Every material Brief change:

1. normalizes the Brief;
2. computes canonical SHA-256 over UTF-8 JSON;
3. compares with the current canonical hash;
4. increments `brief_version` only if content changed;
5. appends one immutable `project_brief_versions` row;
6. emits `project.brief.updated` in the same business transaction.

A direct UPDATE or DELETE of `project_brief_versions` is rejected by a PostgreSQL trigger. Historical AgentRun records can therefore point to the Brief version used at launch without later user edits rewriting history.

## 5. Project settings

P0 Project settings are strict and provider-neutral:

```text
default_locale
timezone
cost_budget_default
quality_profile
model_policy_id
data_retention_profile
```

Unknown keys are rejected. API keys, passwords, private keys, provider tokens and similar secrets do not belong in Project settings.

## 6. Authentication and tenant authorization

`X-Lumi-Organization-Id` is a tenant selector only. It is never authorization.

The runnable Project app overrides the generic transport context with NODE-16 authentication:

### Browser session

```text
opaque lumi_session cookie
-> server-side Session
-> active Organization membership
-> Role/Permission reconstruction
-> project.read / project.write
-> Origin + X-CSRF-Token for mutation
```

### API token

```text
Bearer lumi_<prefix>_<secret>
-> hashed token lookup and validation
-> organization match
-> project.read / project.write scope
```

A cross-tenant project ID is never resolved without the authenticated organization predicate.

## 7. Project create transaction

`ProjectService.create_project` writes in one SQLAlchemy transaction:

```text
IdempotencyOperation
Project
ProjectBriefVersion #1
ProjectSummary
project.created OutboxEvent
project.created AuditEvent
```

The idempotency key is bound to a canonical request hash. Reusing the same key with a different create payload is rejected. Repeating the identical completed request resolves to the original Project.

## 8. Optimistic concurrency

Mutable Project operations require an expected version (`If-Match` at HTTP boundary).

The write uses a compare-and-swap predicate containing:

```text
project.id
organization_id
expected version
deleted_at IS NULL
```

A stale version produces a conflict instead of last-write-wins data loss.

## 9. Archive, restore and deletion

`DELETE /api/v1/projects/{id}` in P0 means archive, not physical deletion.

Archive:

- sets Project status to `archived`;
- preserves assets/artifacts/history;
- prevents paid commands;
- emits lifecycle event/audit.

Restore:

- is explicit;
- changes `archived -> paused`;
- preserves history;
- does not automatically resume paid work.

`deleted_at` remains a separate soft-delete/retention boundary for later deletion/GC workflows. NODE-17 does not cascade-delete project assets.

## 10. Paid-command guard

The Project-level prerequisite for a paid generation or similar command is:

```text
status == active
AND deleted_at IS NULL
```

NODE-17 exposes this as a service guard. Later Agent/Generation nodes must call it before reserving or spending provider budget. `paused`, `draft` and `archived` Projects cannot start paid work.

## 11. List/search and cursor

P0 Project list supports:

```text
status
workspace_id
created_by
updated_after
updated_before
q (name ILIKE)
cursor
limit 1..100
```

Cursor ordering is deterministic over `(created_at DESC, id DESC)`. Cursor data is opaque URL-safe base64 JSON and carries a version marker.

Semantic Project search is intentionally not implemented in NODE-17.

## 12. Project Summary projection

`project_summaries` is a rebuildable/eventually-consistent query projection:

```text
latest_artifact_preview_id
last_activity_at
active_run_count
artifact_count
```

It is not a billing, rights or provenance source of truth. Project list should evolve toward this projection instead of joining all heavy Artifact/Agent tables.

## 13. Events

NODE-17 produces the frozen event names:

```text
project.created
project.updated
project.paused
project.archived
project.restored
project.brief.updated
```

Events are written to the transactional outbox. Publishing is owned by the later outbox/event runtime.

## 14. HTTP surface

Implemented Project operations:

```text
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
POST   /api/v1/projects/{project_id}:restore
GET    /api/v1/projects/{project_id}/brief/versions
```

Other existing `/api/v1` contract routes remain explicit `501 APPLICATION_SERVICE_NOT_INSTALLED` in the NODE-17 runtime until their owner nodes are implemented.

## 15. Runnable local app

Entrypoint:

```text
lumi_api.project_app:app
```

It combines:

- NODE-16 canonical Auth router;
- Mailpit-compatible development verification/reset/invite delivery;
- authenticated Project context;
- ProjectCoreGateway;
- PostgreSQL persistence.

## 16. Validation split

### Project Contract

Dependency-free Python 3.12 gate:

```text
compileall
Project JSON contract validator
stdlib Project Core unit tests
```

It deliberately does not depend on `uv.lock`.

### Project Integration

Full environment gate:

```text
uv sync --all-packages --frozen
ruff
pyright
PostgreSQL startup
Alembic upgrade to head
alembic/ORM drift check
seed
persistence schema checks
Project transaction/lifecycle tests
Project Auth/Tenant/CSRF tests
```

This gate must run successfully before NODE-17 can be marked COMPLETE.

## 17. Current external blockers

GitHub hosted Actions are currently unable to start because account Actions billing/spending requires attention. No CI PASS is claimed while runners do not execute.

The repository `uv.lock` is intentionally stale from the earlier database/auth work and now also lacks `lumi-project-core`. It must be genuinely regenerated with `uv lock`; it must not be hand-edited.

## 18. Downstream contracts

NODE-18 Asset Storage must use Project as the project/tenant scope and must not treat archive as asset deletion.

Agent/Generation runtime must persist `project_id`, capture the launch `brief_version`, and call the paid-command guard before spending provider budget.

Artifact/Canvas runtime continues to use NODE-13 Design IR and NODE-15 Artifact Version/Provenance while resolving them under this Project scope.

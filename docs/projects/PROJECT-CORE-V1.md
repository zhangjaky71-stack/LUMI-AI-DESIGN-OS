# LUMI Project Core V1

Status: **FROZEN CONTRACT / NODE-17**  
Depends on: NODE-10 Database, NODE-11 API Contract, NODE-16 Authentication & Tenant Isolation

## 1. Project is the durable work container

Every design, Task, AgentRun, Generation, Artifact and project-scoped Asset must resolve through a Project. A chat/thread may be a UI surface, but it is not project truth.

P0 lifecycle:

```text
DRAFT -> ACTIVE | ARCHIVED
ACTIVE -> PAUSED | ARCHIVED
PAUSED -> ACTIVE | ARCHIVED
ARCHIVED -> ACTIVE only through explicit restore
```

Archive is logical retention state. It does not synchronously delete Assets, Artifacts, AgentRuns or other history.

## 2. Structured Brief

`lumi.project-brief/1.0` freezes:

```text
objective
audience
brand_context
deliverables
channels
visual_direction
copy_requirements
constraints
references
locale
notes
source_input_hash?
source_input_ref?
```

Raw source text may be retained behind an access-controlled reference. Agent/runtime decisions should consume the structured Brief and its exact version.

Brief list fields are canonicalized and duplicate semantic entries are rejected. The raw prompt itself is not required in every Project row.

## 3. Brief versioning

Every Project starts at `brief_version = 1`. A material Brief change creates an append-only `project_brief_versions` row and increments the Project's current brief version. Changes to name/settings without Brief changes do not create a fake Brief version.

An AgentRun must freeze the Project Brief version it started with. NODE-17 persists this in `agent_run_project_context.project_brief_version`; later Brief edits never rewrite old run context.

The application role has SELECT+INSERT, but no UPDATE/DELETE permission on Brief history.

## 4. Project settings

`lumi.project-settings/1.0` freezes:

- `default_locale`
- `timezone`
- `cost_budget_default`
- `cost_budget_currency`
- `quality_profile`: `fast | balanced | high`
- `model_policy_id?`
- `data_retention_profile`: `standard | extended | restricted`

Provider API keys, passwords, access tokens and other secrets do not belong in Project settings.

## 5. Tenant and authorization boundary

A Project command is accepted only when all layers agree:

1. NODE-16 authenticates the Principal;
2. `AccessPolicyService` authorizes `project.read` or `project.write`;
3. Repository operations are explicitly scoped by `organization_id`;
4. Workspace and Brand references resolve inside the same organization;
5. PostgreSQL tenant session sets `app.current_organization_id`;
6. RLS limits rows to the selected tenant;
7. NODE-17 same-tenant triggers reject new Project Core rows that reference a Project/AgentRun from another tenant.

Cross-tenant and absent resources are intentionally not enumerable through resource resolution.

## 6. Create transaction

A production create transaction must atomically create:

```text
Project
+ Project Brief v1
+ Project default branch metadata (name = main)
+ Project Summary seed
+ project.created Outbox event
+ Audit event
```

`projects.active_branch_id` is **not** populated during empty Project creation because that FK points to an actual `artifact_branches` row, which cannot exist before an Artifact exists. `project_branch_defaults` stores the default branch preference until the first durable Artifact branch is created.

Failure of any required write rolls back the whole creation transaction.

## 7. Optimistic concurrency

Project mutations require an expected version (`If-Match` at the HTTP boundary). A successful mutation increments `projects.version` exactly once. Stale mutations return a conflict rather than silently overwriting newer state.

Brief version and Project optimistic version are distinct:

- Project `version`: every material Project mutation;
- `brief_version`: only material Brief changes.

## 8. Archive, pause and paid execution

Archive and Pause do not delete existing runs. They block creation of new paid execution.

NODE-17 enforces this in both application service and PostgreSQL triggers on new `agent_runs` and `generations` rows. Restore is explicit and produces `project.restored`.

`DELETE /api/v1/projects/{id}` means archive. It is not physical deletion.

## 9. Default branch metadata

`project_branch_defaults` contains one row per Project and defaults to `main`. It is not an Artifact branch and has no fake Artifact ID.

When an Artifact/DesignDocument is created later, the artifact subsystem may create its real branch and update `projects.active_branch_id` to that legitimate `artifact_branches.id`.

## 10. Project summary projection

`project_summaries` is a lightweight eventual projection for project-list UX:

```text
latest_artifact_preview_id?
last_activity_at
active_run_count
artifact_count
projection_version
```

It is deliberately not financial or approval truth. Listing Projects does not need to join every heavy Artifact/AgentRun table.

## 11. List/search contract

P0 supports:

- status
- workspace
- creator
- updated-from / updated-to
- case-insensitive name query
- cursor
- limit 1..100

The cursor is based on a stable `(updated_at, id)` order. Production PostgreSQL indexes include organization/update and workspace/update access paths. Semantic Project search remains out of scope for P0.

## 12. Events

Exactly these Project Core event names are frozen:

```text
project.created
project.updated
project.paused
project.archived
project.restored
project.brief.updated
```

They are written through the existing Outbox pattern so event publication does not race the database transaction.

## 13. HTTP surface

NODE-17 extends the existing `/api/v1` Project contract with:

```text
GET    /projects
POST   /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}                  # archive
POST   /projects/{id}/transitions
POST   /projects/{id}/restore
GET    /projects/{id}/brief/versions
```

The routes remain behind NODE-16's central Auth/Tenant Guard.

## 14. Persistence migration

NODE-17 adds forward migration `20260816_0003` on top of NODE-16 `0002`. It does not rewrite the frozen `0001` or `0002` history.

It adds:

- `projects.brief_version`
- `projects.archived_at`
- `project_brief_versions`
- `project_branch_defaults`
- `project_summaries`
- `agent_run_project_context`
- list/search indexes
- RLS for all new tenant tables
- same-tenant trigger guards
- archive/pause paid-command trigger guards
- least-privilege runtime grants
- deterministic migration backfill for existing Projects and AgentRuns

Existing Project UUIDv7 identifiers are reused for baseline migrated Brief/Main metadata IDs, avoiding a UUIDv4 exception during migration.

## 15. Validation evidence contract

Hosted validation must execute, not merely exist. NODE-17 requires:

- frozen Python 3.12 workspace install;
- static architecture validator;
- Project Core service tests;
- authenticated FastAPI lifecycle tests;
- API baseline regression tests;
- JSON Schema export and parse;
- Ruff and Pyright on NODE-17 scope;
- PostgreSQL `0003` upgrade and invariant suite;
- downgrade to `0002`;
- reapply `0003` and rerun invariants;
- repository CI/security gates.

No `COMPLETE` status is allowed while GitHub Actions cannot allocate a runner.

## 16. Explicit runtime boundary

The repository currently has a deterministic MemoryProjectRepository plus ProjectApiAdapter and the production PostgreSQL schema/invariants. A production async SQL ProjectRepository/composite `ApiV1Service` binding remains a visible runtime integration item until the repository's persistence dependencies are frozen and the adapter is exercised against PostgreSQL.

Next: **NODE-18 — Asset Storage**.

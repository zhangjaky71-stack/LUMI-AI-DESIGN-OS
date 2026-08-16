# Project Core Persistence Mapping V1

NODE-17 extends the NODE-10/NODE-16 PostgreSQL baseline only through forward migration `20260816_0003`.

## Project row

`projects` remains the aggregate root table. NODE-17 adds:

- `brief_version INTEGER NOT NULL DEFAULT 1`
- `archived_at TIMESTAMPTZ NULL`
- positive Brief version CHECK
- archive timestamp/status consistency CHECK

The existing `version` column remains optimistic concurrency state. `deleted_at` is not used as the normal Project Archive timestamp; physical-retention workflows remain separate.

## Structured Brief history

`project_brief_versions` persists immutable historical Brief snapshots:

```text
id
organization_id
project_id
version_number
brief_json
changed_by?
change_reason?
created_at
```

Uniqueness: `(project_id, version_number)`. Runtime permission: SELECT + INSERT only for `lumi_app`.

## Default branch preference

`project_branch_defaults` stores one Project-level default branch name (`main`). It intentionally does not reference `artifact_branches` and therefore cannot create a dangling Artifact FK during empty Project creation.

## List projection

`project_summaries` is one row per Project and includes only list/UI aggregate values. It is a projection and is not used as accounting, approval or provenance truth.

## AgentRun Brief snapshot

`agent_run_project_context` records:

```text
organization_id
agent_run_id
project_id
project_brief_version
created_at
```

This freezes the Project requirement snapshot for historical AgentRuns without rewriting the NODE-10 `agent_runs` table contract.

## RLS and same-tenant references

All four new tenant tables enable PostgreSQL RLS against `lumi_current_organization_id()`. A security-definer same-tenant trigger also verifies that referenced Projects—and for AgentRun context, AgentRuns—belong to the row organization.

RLS controls row visibility; the same-tenant trigger controls relational integrity. Both are required.

## Paid command guard

`trg_agent_runs_project_paid_command_guard` and `trg_generations_project_paid_command_guard` reject new rows when Project status is `paused` or `archived`. This is a database backstop for the application-level Project status guard.

## Migration compatibility

Existing Projects receive:

- `brief_version = 1`
- a Brief v1 snapshot from current `brief_json`
- a `main` Project branch default
- a seeded summary projection

Existing AgentRuns receive a context row pointing at the Project's current migration-time Brief version.

The baseline Brief/default IDs are normalized to the existing Project ID. Since Project IDs are already UUIDv7-shaped in the platform contract, migration does not introduce UUIDv4-only historical rows.

## Runtime integration gap

The schema, RLS, migration and database invariants are production-oriented, but the API workspace does not yet freeze an async SQLAlchemy/asyncpg persistence dependency in `apps/api/pyproject.toml`. Therefore NODE-17 does not claim that `ProjectApiAdapter` is production-bound to PostgreSQL yet. That binding is tracked in the NODE-17 gap ledger rather than hidden behind a Memory repository.

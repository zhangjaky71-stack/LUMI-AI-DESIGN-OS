# NODE-17 — Project Core Acceptance

Status: **IMPLEMENTED / VALIDATING**  
Hosted status: **expected BLOCKED_EXTERNAL until a runner is allocated and executes**

## Implemented

- Structured `lumi.project-brief/1.0` contract.
- Structured `lumi.project-settings/1.0` contract.
- Project aggregate record with optimistic version and independent Brief version.
- Append-only Brief history contract.
- Project-level default `main` branch metadata without dangling Artifact FK.
- Project summary projection contract.
- Project event contract for created/updated/paused/archived/restored/brief-updated.
- Tenant-aware Project repository protocol.
- Workspace and Brand same-tenant resolution before Project creation/update.
- Central NODE-16 permission checks through `AccessPolicyService`.
- DRAFT/ACTIVE/PAUSED/ARCHIVED lifecycle including explicit restore.
- Archive/Pause paid-command block in service.
- Stable cursor pagination and P0 filters.
- `ProjectApiAdapter` for the Project methods of the composite `ApiV1Service`.
- REST extensions: Brief history, DELETE=archive, restore, list filters.
- Forward migration `20260816_0003` on NODE-16 `0002`.
- `projects.brief_version` and `projects.archived_at`.
- `project_brief_versions`, `project_branch_defaults`, `project_summaries`, `agent_run_project_context`.
- PostgreSQL RLS on all four new tenant tables.
- PostgreSQL same-tenant trigger guards.
- PostgreSQL paid-command guards on new AgentRun/Generation creation.
- Brief history UPDATE/DELETE revoked from application role.
- Existing Project/AgentRun migration backfill.
- UUIDv7-compatible baseline backfill normalization.
- Service/adversarial contract tests.
- Authenticated FastAPI Project lifecycle test.
- PostgreSQL invariant test harness.
- 7 machine-readable JSON Schema exports.
- Static architecture/migration/API validator.

## Validation commands required for canonical PASS

```bash
uv sync --all-packages --frozen
PYTHONPATH=apps/api/src uv run python tools/node17/validate_project_core.py
PYTHONPATH=apps/api/src uv run pytest -q \
  apps/api/tests/test_project_core_contract.py \
  apps/api/tests/test_project_core_http.py \
  apps/api/tests/test_api_v1_contract.py
rm -rf reports/nodes/NODE-17/generated-schemas
PYTHONPATH=apps/api/src uv run python tools/node17/export_project_schemas.py
uv run ruff check apps/api/src/lumi_api/projects \
  apps/api/src/lumi_api/api/v1/routes.py \
  apps/api/src/lumi_api/api/v1/schemas.py \
  apps/api/tests/test_project_core_contract.py \
  apps/api/tests/test_project_core_http.py \
  tools/node17
uv run pyright apps/api/src/lumi_api/projects \
  apps/api/src/lumi_api/api/v1/routes.py \
  apps/api/src/lumi_api/api/v1/schemas.py \
  apps/api/tests/test_project_core_contract.py \
  apps/api/tests/test_project_core_http.py \
  tools/node17
```

Hosted database gate must additionally execute:

```text
start local PostgreSQL
alembic upgrade head -> must be 20260816_0003
load deterministic two-tenant fixture
run tools/node17/test_project_database.py
alembic downgrade 20260816_0002
verify NODE-17 objects removed and NODE-16 objects survive
alembic upgrade head
reload fixture
rerun tools/node17/test_project_database.py
```

## Required evidence before COMPLETE

- Python 3.12 frozen install actually executes successfully.
- Project Core validator green.
- Project service tests green.
- Authenticated HTTP tests green.
- NODE-11 API regression green after forward extension.
- Seven generated schemas parse successfully.
- Ruff green.
- Pyright green.
- PostgreSQL upgrade/invariants/downgrade/reapply green.
- Repository CI/security green.
- NODE-09 through NODE-16 stacked dependencies resolved.

## Explicit gaps

See `reports/nodes/NODE-17/gap-ledger.json`.

Most importantly, this node does **not** claim a production PostgreSQL ProjectRepository binding or durable project-create idempotency replay yet. It also does not claim the eventual summary projector worker is running.

## Completion rule

Do not mark NODE-17 `COMPLETE` from static code review, a workflow file, or a job that never received a runner. `runner_id=0 / steps=[]` is `BLOCKED_EXTERNAL`, not PASS.

Next: **NODE-18 — Asset Storage**.

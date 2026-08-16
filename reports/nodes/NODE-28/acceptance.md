# NODE-28 Acceptance — LangGraph Control Plane

Status: `IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

## Scope implemented

- Real `StateGraph` main control plane with exact `lumi.main@1.0.0` identity.
- Stable AgentRun `thread_id` contract.
- Small/bounded `LumiRunState` with IDs and references only.
- Explicit deterministic / agentic / side-effect / external-wait / human-interrupt node categories.
- LangGraph checkpoint and same-thread resume adapter.
- Testing-only in-memory saver and fail-closed production PostgreSQL saver composition seam.
- Human approval interrupt.
- Long-running external-job checkpoint/yield/resume contract without polling.
- Graph definition/version/code-SHA provenance fences.
- Resume `resume_version` and checkpoint CAS.
- Operation replay seams for start/resume/cancel.
- Safe public event contract with private-reasoning rejection.
- Tenant-aware PostgreSQL run-control projection with RLS.
- AgentRun status projection and cancellation callbacks.
- Authenticated command-only API surface for resume/cancel.
- Migration `20260816_0010` stacked on `20260816_0009`.

## Source evidence

### Agent runtime

- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/contracts.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/errors.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/events.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/ports.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/main_graph.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/runtime.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/checkpointing.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/postgres_store.py`
- `apps/agent-runtime/src/lumi_agent_runtime/control_plane/testing.py`

### Database

- `apps/api/migrations/versions/20260816_0010_langgraph_control_plane.py`
- `apps/api/migrations/versions/20260816_0010_sql/up_01.sql`
- `apps/api/migrations/versions/20260816_0010_sql/up_02.sql`
- `apps/api/migrations/versions/20260816_0010_sql/down_02.sql`
- `apps/api/migrations/versions/20260816_0010_sql/down_01.sql`
- `apps/api/src/lumi_api/persistence/models_control_plane.py`
- `apps/api/src/lumi_api/persistence/models_execution.py`

### API

- `apps/api/src/lumi_api/api/v1/agent_run_schemas.py`
- `apps/api/src/lumi_api/api/v1/agent_run_dependencies.py`
- `apps/api/src/lumi_api/api/v1/agent_run_routes.py`
- `apps/api/src/lumi_api/api/v1/app.py`

## Test evidence authored

### Unit / behavior

`apps/agent-runtime/tests/test_control_plane_node28.py` covers:

- complete deterministic mock run,
- start operation replay,
- approval interrupt and same-thread resume,
- stale resume version rejection,
- same resume operation replay after checkpoint advancement,
- external-job interrupt/resume,
- interrupted-node re-execution with stable idempotent external job identity,
- graph-version drift rejection,
- cancellation callbacks,
- binary/data-URI/unknown Graph State rejection,
- private-reasoning event rejection,
- production saver strict-mode fail-closed behavior.

### API contract

`apps/api/tests/test_agent_run_control_node28.py` proves the public control API is command
only and does not expose raw checkpoint or arbitrary state mutation endpoints.

### PostgreSQL failure injection

`tools/node28/test_control_plane_database.py` is intended to run against the real compose
PostgreSQL and verifies:

- migration owner can seed graph/run fixtures,
- `lumi_app` can persist its own run-control projection,
- tenant B cannot load tenant A control state,
- stale resume-version CAS fails,
- matching checkpoint + resume-version CAS succeeds,
- AgentRun status projection advances,
- durable control state remains queryable in the owning tenant.

The dedicated workflow additionally performs a `0010 -> 0009 -> 0010` round trip before
any NODE-28 durable state exists, then proves downgrade is refused after run-control state
has been written.

## Architecture/static evidence

`tools/node28/validate_langgraph_control_plane.py` checks:

- exact graph key/version,
- expected graph nodes/categories,
- `interrupt()` and `Command(resume=...)`,
- idempotent side-effect and external-job port names,
- strict production saver guard,
- tenant session context in PostgreSQL store,
- checkpoint/resume CAS markers,
- bounded/closed Graph State contract,
- private-reasoning event guard,
- no provider SDK or direct HTTP client imports in control-plane source,
- migration chain and RLS markers,
- loss-aware downgrade guard,
- exactly eight explicit gaps,
- current package gaps remain visible rather than hidden by an unreviewed lockfile edit.

## Generated schemas

`tools/node28/export_control_plane_schemas.py` exports exactly six Draft 2020-12 schemas:

1. `run-state.schema.json`
2. `start-run-command.schema.json`
3. `resume-run-command.schema.json`
4. `interrupt.schema.json`
5. `run-control-snapshot.schema.json`
6. `safe-run-event.schema.json`

## Security / correctness properties

- No provider secrets are accepted by Graph State.
- No binary state is accepted.
- No arbitrary state keys are accepted.
- No chain-of-thought/private reasoning is emitted in public events.
- Control-store reads require an organization id and set PostgreSQL RLS context.
- Graph definitions are read-only to the normal app role.
- Control rows must reference a published enabled graph definition and match its content
  hash and code SHA.
- Resume requires exact thread/graph identity and an active interrupt id.
- Checkpoint id is a CAS fence, not part of idempotency request identity.
- Long jobs do not poll inside the graph.
- Side-effect ports are explicitly idempotent.
- Cancellation releases pending work/reservations before the control projection is marked
  cancelled.

## Explicit non-claims

The following are **not** claimed complete in NODE-28:

- production `langgraph-checkpoint-postgres` package/lock integration,
- production agent-runtime asyncpg package/lock integration,
- production API/runtime dependency composition,
- production NODE-20 OperationGuard adapter,
- production approval authorization domain binding,
- NODE-19 job-completion wake adapter,
- realtime durable event transport / LangSmith operational dashboards,
- Deep Agents specialist implementation,
- Recipe Engine and Task Graph business implementation.

See `gap-ledger.json` for the exact eight gaps.

## Hosted validation status

GitHub Actions remains blocked before runner allocation by the repository account
payment/spending-limit condition. A job with `runner_id=0` and `steps=[]` is not a test
failure and is not a PASS. The final exact-head hosted run/job evidence must be appended
to PR #95 after the branch is frozen.

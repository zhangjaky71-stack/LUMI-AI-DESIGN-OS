# NODE-33 — Task Graph & Scheduler Acceptance

> Branch: `node-33-task-graph-delivery`  
> Base: `node-32-recipe-engine`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Completion rule: required contract, quality and PostgreSQL gates must actually execute green.

## 1. Scope

NODE-33 turns the immutable NODE-32 `TaskGraphTemplate` into the durable project execution ledger used by LUMI AI DESIGN OS.

Implemented scope:

- Recipe -> TaskGraph instantiation;
- frozen Recipe/TaskGraph provenance;
- deterministic compiled Task IDs;
- durable Task/Dependency/Attempt persistence;
- recoverable DB-backed scheduler;
- ALL / ANY / MIN_SUCCESS readiness;
- NODE-32 safe condition evaluation;
- PostgreSQL `FOR UPDATE SKIP LOCKED` claim;
- state-version CAS;
- lease/heartbeat/reclaim;
- retry and stable NODE-20 logical operation identity;
- WAIT/resume;
- cooperative cancellation;
- bounded durable dynamic child Tasks;
- parallel concurrency groups;
- NODE-19 transactional outbox;
- direct Timeline query;
- ORM/Alembic schema alignment;
- NODE-27 paid-budget admission boundary;
- deterministic unit/integration/DB acceptance definitions.

## 2. Critical invariants implemented

### One Task ledger

NODE-33 reuses existing `tasks` and `task_dependencies`; migration `0015_task_graph_runtime.py` does not create a second Task table.

### Stable logical operation identity

Retry attempts use:

```text
task:<graph_id>:<task_id>
```

Attempt number is not part of the logical idempotency key.

### No blind paid retry

Expired leases record `provider_reconciliation_required=true`. Paid repetition remains subject to NODE-20 reconciliation/idempotency.

### Durable paid-budget admission

NODE-33 carries Task/Recipe budget upper bounds and concurrency limits. Provider-cost admission remains NODE-27 `CostAccountingPort.reserve_provider_cost` / `LedgerBudgetGuard`, so concurrent paid operations use the existing durable reservation ledger rather than a second TaskGraph billing implementation.

### Durable scheduling rules

`condition_expression`, dependency edges, join metadata, concurrency limits and Task state are persisted. `DurableTaskGraphScheduler` reconstructs Task snapshots after restart and reuses the same NODE-33 join/condition rules before promoting PENDING Tasks to READY.

### Concurrent claim

PostgreSQL claim uses:

```text
FOR UPDATE SKIP LOCKED
LIMIT 1
state_version CAS
```

The one-row transaction loop makes each subsequent selection see earlier Tasks already RUNNING and therefore enforces concurrency-group limits inside a batch.

## 3. Runtime implementation evidence

Primary package:

`apps/agent-runtime/src/lumi_agent_runtime/task_graph/`

Required runtime modules are contract-checked as physically present:

- `errors.py`
- `events.py`
- `task_contracts.py`
- `graph_contracts.py`
- `instantiator.py`
- `states.py`
- `state_machine.py`
- `lifecycle.py`
- `claims.py`
- `complete_fail.py`
- `wait_progress.py`
- `cancellation.py`
- `dynamic.py`
- `memory_store.py`
- `postgres_store.py`
- `scheduler.py`
- `__init__.py`

Public durable scheduler:

`DurableTaskGraphScheduler`

Public durable store:

`PostgresTaskGraphStore`

Reference pure store:

`InMemoryTaskGraphStore`

## 4. State contracts

Task states:

```text
PENDING
READY
RUNNING
WAITING_APPROVAL
WAITING_INPUT
WAITING_EXTERNAL
SUCCEEDED
FAILED_RETRYABLE
FAILED_FINAL
CANCELLED
SKIPPED
```

Graph states:

```text
RUNNING
WAITING
SUCCEEDED
FAILED_FINAL
CANCELLED
```

The static validator checks the exact Task state vocabulary.

## 5. Persistence evidence

Migration:

`apps/api/alembic/versions/0015_task_graph_runtime.py`

Creates:

- `task_graph_instances`
- `task_attempts`

Extends existing `tasks` with Graph identity, owner, upper-bound budget, output schema, `condition_expression`, metadata, state-version, lease, retry, wait, cancellation, progress, dynamic and concurrency fields.

TaskAttempt database identity:

```text
UNIQUE(task_id, attempt_number)
```

`logical_operation_key` is intentionally not unique because all attempts of one logical Task reuse it.

Runtime role may update active Attempt status but cannot delete attempt history.

## 6. ORM alignment evidence

- `apps/api/src/lumi_api/persistence/models/workflow.py` maps NODE-33 Task columns.
- `apps/api/src/lumi_api/persistence/models/task_graph.py` defines `TaskGraphInstance` and `TaskAttemptRecord`.
- `apps/api/src/lumi_api/persistence/models/__init__.py` imports/exports both models.
- PostgreSQL CI runs `alembic check` and an explicit metadata assertion for `condition_expression`.

## 7. NODE-19 outbox compatibility

NODE-33 uses the existing canonical outbox columns:

```text
event_name
aggregate_type
aggregate_id
schema_version
payload_json
publish_attempts
```

The static/contract tests explicitly reject old non-canonical aliases such as `event_type`.

## 8. Unit test evidence present

### `test_task_graph_runtime.py`

Covers dependency order, progress, completion, retry logical-key reuse, lease expiry/reconciliation and restart-like behavior.

### `test_task_graph_join_condition.py`

Covers ALL, ANY, MIN_SUCCESS, impossible join and safe condition branches.

### `test_task_graph_control.py`

Covers WAIT/resume, cooperative running cancellation and dynamic budget/concurrency/child limits.

### `test_task_graph_scheduler.py`

Covers durable row reconstruction, persisted condition recovery and scheduler readiness-before-claim orchestration.

### `test_task_graph_postgres_contract.py`

Locks canonical schema names, SKIP LOCKED/CAS, stable logical key, durable condition/cancellation, attempt-history rules and public durable scheduler behavior.

## 9. Integration evidence present

### NODE-32 -> NODE-33 deterministic integration

`scripts/integration_task_graph_recipe.py`

Uses the real NODE-32 production Recipe catalog, instantiates TaskGraph, exercises approval wait/resume, bounded render concurrency, attempts/events and graph completion.

### PostgreSQL scheduler integration

`scripts/integration_task_graph_postgres.py`

Designed to verify:

1. migrate/seed real project fixtures;
2. install a real NODE-32 `product-visuals` TaskGraph;
3. reload Graph/Tasks from PostgreSQL;
4. race multiple scheduler claimers;
5. claim each render Task exactly once;
6. retry one Task;
7. persist attempts 1 and 2 with one logical operation key;
8. query Timeline;
9. verify canonical outbox events;
10. verify `lumi_app` cannot delete TaskAttempt history.

## 10. Static validator

`scripts/validate_task_graph_contract.py`

Release-blocking checks include:

- required runtime files exist;
- exact Task states;
- public durable scheduler;
- stable logical operation key;
- reuse of existing Task ledger;
- NODE-33 migration columns/indexes/permissions;
- canonical Task/Dependency/Outbox schema;
- `condition_expression` persistence;
- Task ORM/model registry alignment;
- SKIP LOCKED/CAS;
- reconciliation marker;
- dynamic Task limits;
- ALL/ANY/MIN_SUCCESS + condition markers;
- NODE-32 `TaskGraphTemplate:v1` handoff;
- no ambient authority imports in TaskGraph runtime.

## 11. CI gates

Workflow:

`.github/workflows/task-graph.yml`

### Gate 1 — `task-graph-contract`

- compile NODE-33 runtime/tests/integrations;
- revalidate NODE-32 Recipe Engine;
- NODE-33 static contract;
- all `test_task_graph_*.py` dependency-light unit tests;
- deterministic Recipe -> TaskGraph integration.

### Gate 2 — `task-graph-quality`

- frozen workspace install;
- pytest;
- Ruff;
- Pyright.

### Gate 3 — `task-graph-postgres`

- repository PostgreSQL infrastructure;
- migration to head;
- `alembic check` metadata drift gate;
- explicit NODE-33 ORM metadata assertion;
- deterministic seed;
- concurrent scheduler/retry integration;
- downgrade/upgrade smoke;
- infrastructure reset.

## 12. Validation status at submission

A current-turn local clone/execution attempt could not reach the private GitHub repository because the execution environment could not resolve `github.com`. That is an environment/network limitation, not a passing or failing test result.

Earlier exploratory NODE-33 runtime work executed local compile/unit checks before the final delivery branch was reconstructed, but **those earlier results are not claimed as validation of this final branch**.

Therefore the final delivery branch requires the GitHub CI gates above to execute before COMPLETE can be claimed.

## 13. Acceptance checklist

- [x] Recipe can instantiate a Task DAG.
- [x] TaskGraph provenance is frozen.
- [x] Existing `tasks` / `task_dependencies` are reused.
- [x] Durable Task/Attempt Graph schema implemented.
- [x] READY scheduler uses persisted dependencies/conditions.
- [x] Scheduler claim uses SKIP LOCKED + CAS.
- [x] Retry preserves logical operation identity.
- [x] Lease expiry requires provider reconciliation.
- [x] WAIT/resume survives persistence boundary.
- [x] Cooperative cancellation implemented.
- [x] Dynamic expansion is bounded and durable.
- [x] Parallel concurrency is enforced at DB claim.
- [x] Timeline is directly queryable.
- [x] NODE-19 outbox integration uses canonical schema.
- [x] NODE-27 remains durable paid-budget admission boundary.
- [x] Unit/integration/static acceptance assets exist.
- [x] Dedicated three-stage CI exists.
- [ ] `task-graph-contract` hosted gate executed green.
- [ ] `task-graph-quality` hosted gate executed green.
- [ ] `task-graph-postgres` hosted gate executed green.
- [ ] Hosted migration downgrade/upgrade smoke executed green.

## 14. Current classification

Until required hosted execution succeeds:

```text
IMPLEMENTED
VALIDATING
not COMPLETE
```

If GitHub Actions fails before runner allocation because of account billing/spending-limit status, classification becomes:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

No hosted PASS is claimed without actual executed steps.

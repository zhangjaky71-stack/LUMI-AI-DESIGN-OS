# LUMI Task Graph Runtime V1

> NODE-33 — Task Graph & Scheduler  
> Runtime contract: `TaskGraph:v1`  
> Depends on: NODE-10 Persistence, NODE-19 Queue/Event Runtime, NODE-20 Idempotency, NODE-27 Cost/Quota, NODE-32 Workflow/Recipe Engine  
> Next: NODE-34 Context Engine

## 1. Purpose

Task Graph is the project-level durable execution ledger for LUMI AI DESIGN OS. NODE-32 freezes the versioned business skeleton as a `TaskGraphTemplate`; NODE-33 instantiates and runs that template as recoverable Tasks.

The boundaries are explicit:

- **Recipe** = deterministic/versioned workflow skeleton.
- **Task Graph** = durable project execution state and scheduler source of truth.
- **Deep Agent Todo** = Agent-local planning aid only.
- **LangSmith** = observability/tracing, not the business state database.

Project Timeline and progress are queried from TaskGraph persistence, never reconstructed from trace text.

## 2. Source of truth

NODE-33 reuses the existing workflow ledger:

- `tasks`
- `task_dependencies`
- NODE-19 `outbox_events`

Migration `0015_task_graph_runtime` adds:

- `task_graph_instances`
- `task_attempts`
- TaskGraph-specific columns to the existing `tasks` table

It does **not** create a second competing Task table.

## 3. Frozen provenance

Each Graph freezes:

- organization/project/agent-run IDs;
- Recipe ID and exact version;
- Recipe definition hash;
- Recipe provenance hash;
- TaskGraphTemplate hash;
- final TaskGraph provenance hash;
- Recipe budget upper bound;
- Task count.

A restarted scheduler reloads this frozen Graph. It does not resolve a newer Recipe/Agent/Skill alias midway through a run.

Compiled Task IDs are deterministic within the Graph:

```text
uuid5(graph_id, "task:<task_key>")
```

Dynamic child identity is deterministic from Graph, parent and child key.

## 4. Task states

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

Terminal Task states are:

```text
SUCCEEDED
FAILED_FINAL
CANCELLED
SKIPPED
```

Graph states are exactly:

```text
RUNNING
WAITING
SUCCEEDED
FAILED_FINAL
CANCELLED
```

There is no Graph `PENDING` state in V1.

## 5. Durable Task fields

NODE-33 preserves legacy canonical columns such as:

```text
type
owner_agent_key
input_json
output_json
budget_reserved
attempt_count
max_attempts
```

and adds durable execution metadata including:

```text
task_graph_id
recipe_step_id
task_key
owner_key
budget_limit_usd
output_schema
condition_expression
metadata_json
state_version
lease_owner
lease_expires_at
heartbeat_at
retry_not_before
wait_reason
external_ref
cancellation_requested_at
progress_current
progress_total
dynamic_depth
dynamic_child_limit
concurrency_group
concurrency_limit
```

`condition_expression` is persisted because a restarted scheduler must be able to re-evaluate whether a PENDING Task can become READY.

## 6. Readiness and durable scheduler

`DurableTaskGraphScheduler` reconstructs Task state from PostgreSQL and reuses the same NODE-33 readiness rules used by the reference runtime.

Readiness includes:

- dependency state;
- ALL / ANY / MIN_SUCCESS join policy;
- NODE-32 safe condition expression;
- retry timing;
- graph cancellation;
- attempt capacity;
- concurrency group limits.

The durable scheduler performs:

```text
reclaim expired leases
-> reload durable tasks/dependencies/conditions
-> promote eligible PENDING -> READY
-> deterministically SKIP impossible/false branches
-> claim READY tasks
```

Business join/condition rules are evaluated before a row is marked READY. The claim SQL does not invent a second Recipe semantics engine.

## 7. Safe conditions

Conditions reuse NODE-32's restricted evaluator. Allowed context roots are bounded data only:

```text
inputs
project
steps
run
```

No `eval`, arbitrary function call, SQL, subprocess, browser, provider SDK or network authority is granted to a condition.

False condition:

```text
PENDING -> SKIPPED
reason = CONDITION_FALSE
```

Impossible join:

```text
PENDING -> SKIPPED
reason = UPSTREAM_JOIN_UNSATISFIED
```

## 8. Concurrent claim

The PostgreSQL scheduler uses a transaction-local loop:

```text
SELECT one READY task
FOR UPDATE SKIP LOCKED
LIMIT 1

-> verify Graph RUNNING
-> verify retry_not_before
-> verify max_attempts
-> verify cancellation
-> verify concurrency group capacity
-> CAS READY -> RUNNING using state_version
-> create TaskAttempt
-> create NODE-19 outbox event
-> repeat up to bounded claim limit
```

Selecting one row at a time inside the transaction is intentional: a second selection sees the first Task already RUNNING, so one batch cannot over-claim the same concurrency group.

Multiple scheduler replicas can race without claiming the same Task.

## 9. State-version CAS

Every Task uses `state_version` compare-and-set semantics:

```text
WHERE id = :task_id
  AND state_version = :expected_version
  AND status = :expected_status

SET state_version = state_version + 1
```

Stale workers/schedulers cannot overwrite a newer state transition.

## 10. Lease and heartbeat

A running Task records:

```text
lease_owner
lease_expires_at
heartbeat_at
```

Heartbeat/completion requires the same active lease owner. A stale worker cannot finish a Task after ownership has expired or moved.

## 11. Lease expiry and paid effects

Lease expiry is an ambiguity boundary, not proof that an external request failed.

NODE-33 marks recoverable expiry with reconciliation evidence:

```text
provider_reconciliation_required = true
failure = lease_expired
```

If attempts are exhausted, the Task becomes `FAILED_FINAL`; otherwise it becomes `FAILED_RETRYABLE`.

A repeated paid side effect must still pass NODE-20 reconciliation/idempotency. NODE-33 never treats lease expiry as permission for blind second billing.

## 12. Stable logical operation identity

The logical side-effect identity is:

```text
task:<graph_id>:<task_id>
```

It does **not** include attempt number.

```text
attempt 1 -> task:GRAPH:TASK
attempt 2 -> task:GRAPH:TASK
attempt 3 -> task:GRAPH:TASK
```

`attempt_number` is execution history only. This lets NODE-20 recognize replay/reconcile/retry-safe behavior for the same logical operation.

## 13. Attempt ledger

`task_attempts` stores:

- Graph/Task/organization identity;
- monotonically increasing attempt number;
- stable logical operation key;
- status/error/result/cost;
- started/completed timestamps.

Database invariant:

```text
UNIQUE(task_id, attempt_number)
```

The logical operation key is intentionally not unique across attempts.

Runtime role may update an active `RUNNING` attempt to its completion/wait/retry state, but cannot delete TaskAttempt history. Store updates are guarded by `status='RUNNING'`.

## 14. Retry

```text
RUNNING
-> FAILED_RETRYABLE
-> READY with retry_not_before
-> RUNNING with next attempt_number
```

The Task ID and logical operation key remain unchanged.

## 15. WAIT and resume

Durable wait states:

```text
WAITING_APPROVAL
WAITING_INPUT
WAITING_EXTERNAL
```

Entering a wait closes the active execution attempt and clears the lease. If no runnable work remains, Graph state becomes `WAITING`.

Resume requires an explicit reference and transitions the same Task to READY. PostgreSQL resume also restores the Graph from `WAITING` to `RUNNING` in the same transactional boundary.

## 16. Cancellation

Graph cancellation is cooperative:

- non-running Tasks cancel immediately;
- RUNNING Tasks receive `cancellation_requested_at`;
- the current worker acknowledges cancellation under its lease.

This avoids pretending an in-flight provider side effect vanished. Existing completed Artifacts are not deleted.

## 17. Dynamic Tasks

Agent-proposed child work can enter the durable Graph only through the TaskGraph boundary.

V1 hard limits:

```text
max dynamic depth = 4
max children per parent = 32
```

Rules:

- parent must be RUNNING;
- parent must allow dynamic children;
- child budget cannot exceed parent budget;
- child concurrency cannot widen parent concurrency;
- child dynamic-child scope cannot widen parent scope;
- child has deterministic identity and `parent_task_id`;
- Graph `task_count` grows atomically;
- event is written to NODE-19 outbox.

The Postgres store exposes durable `add_dynamic_task`, so dynamic work is not an in-memory-only feature.

## 18. Parallel concurrency

NODE-32 fan-out metadata is materialized as:

```text
concurrency_group
concurrency_limit
```

Before each claim the scheduler counts RUNNING Tasks in the same Graph/group. The limit therefore holds across scheduler replicas, not merely within one process.

## 19. Budget boundary

NODE-33 carries Recipe/Task budget upper bounds and constrains parallelism. It does **not** create a second billing ledger.

The authoritative paid-operation admission is NODE-27:

```text
CostAccountingPort.reserve_provider_cost(...)
LedgerBudgetGuard
```

NODE-27 performs durable provider-cost reservation before provider acceptance. This is the atomic protection against concurrent Tasks simultaneously spending the same remaining budget.

Cross-node order for paid work is therefore:

```text
NODE-32 bounded workflow
-> NODE-33 durable READY/claim/concurrency
-> NODE-20 logical idempotency/reconciliation
-> NODE-27 durable cost reservation
-> NODE-22 / NODE-25 paid side effect
```

No TaskGraph code is allowed to bypass the durable cost/idempotency boundary.

## 20. Progress

Task progress uses only meaningful denominators:

```text
progress_current
progress_total
```

Project progress derives from durable Task states. The UI must not fabricate percentages from tokens, trace spans or elapsed time.

## 21. NODE-19 outbox

NODE-33 uses the existing canonical outbox columns:

```text
event_name
aggregate_type
aggregate_id
schema_version
payload_json
publish_attempts
```

State and event writes are transactionally coupled where the Postgres store changes state.

Events include:

```text
task.ready
task.started
task.waiting
task.progress
task.retry_scheduled
task.succeeded
task.failed
task.skipped
task.cancelled
task.dynamic_created
task_graph.completed
```

## 22. Restart and recovery

`PostgresTaskGraphStore` provides:

- graph load;
- Task/dependency readback;
- attempt readback;
- Timeline query;
- claim;
- heartbeat;
- READY CAS;
- completion/wait/failure;
- wait resume;
- retry scheduling;
- lease reclaim;
- durable dynamic child creation;
- cancellation.

`DurableTaskGraphScheduler` reconstructs `TaskSnapshot` rows, including `condition_expression`, and performs readiness before claim. A process restart therefore does not require an in-memory Agent plan to continue project execution.

## 23. Timeline

Timeline is directly queryable from durable Tasks/Attempts and includes:

- Task key / Recipe step;
- type / exact owner;
- state;
- priority;
- progress;
- attempt count;
- start/finish timestamps;
- wait reason / external reference;
- persisted attempt count.

## 24. ORM alignment

API metadata includes:

- extended `Task`;
- `TaskGraphInstance`;
- `TaskAttemptRecord`.

`lumi_api.persistence.models` imports the new models so `alembic check` can detect schema drift. `condition_expression` is present in migration, ORM and Postgres store.

## 25. Security boundary

The TaskGraph runtime package imports no ambient provider/database/network authority such as:

- asyncpg;
- SQLAlchemy;
- psycopg;
- provider SDKs;
- requests;
- Docker/subprocess.

`PostgresTaskGraphStore` accepts an injected DB connection protocol. Credentials remain in trusted API/worker configuration, not Agent or Recipe definitions.

## 26. Validation gates

### `task-graph-contract`

- compile runtime/tests/integrations;
- revalidate NODE-32 Recipe Engine;
- NODE-33 static contract;
- dependency-light TaskGraph unit tests;
- deterministic Recipe -> TaskGraph integration.

### `task-graph-quality`

- frozen workspace install;
- pytest;
- Ruff;
- Pyright.

### `task-graph-postgres`

- start repository PostgreSQL infrastructure;
- migrate to head;
- `alembic check` ORM drift gate;
- deterministic seed;
- concurrent scheduler claim integration;
- retry/logical-key/outbox/Timeline evidence;
- attempt-history permission check;
- downgrade/upgrade smoke.

## 27. PostgreSQL acceptance race

The dedicated integration uses the real NODE-32 `product-visuals` Recipe and isolates its render fan-out for the DB race test. Multiple scheduler claimers run concurrently.

Acceptance requires:

- every eligible render Task claimed exactly once;
- no duplicate Task ID;
- concurrency upper bound respected;
- retry produces attempt 2 for the same Task;
- both attempts reuse the same logical operation key;
- Timeline can be queried after persistence;
- canonical outbox rows exist;
- `lumi_app` cannot delete attempt history.

## 28. Release-blocking invariants

1. Recipe provenance is frozen at Graph instantiation.
2. There is one durable Task ledger, not a duplicate NODE-33 Task table.
3. Dependency/join/condition rules run before READY.
4. A READY Task can have at most one active worker claim.
5. Scheduler replicas use `FOR UPDATE SKIP LOCKED` plus CAS.
6. Lease expiry requires reconciliation, not blind paid retry.
7. Retry reuses the same logical operation key.
8. Attempt number is history, not idempotency identity.
9. WAIT state survives restart and resume restores Graph RUNNING.
10. Dynamic expansion is bounded and cannot widen authority/budget/concurrency.
11. Paid admission remains NODE-27 durable reservation.
12. Cancellation is cooperative for RUNNING work.
13. Timeline is queryable without parsing traces.
14. Migration, ORM and runtime use canonical existing schema names.
15. NODE-33 is never marked COMPLETE until the required execution gates actually run green.

## 29. Non-goals

NODE-33 does not implement:

- prompt/context assembly;
- vector retrieval;
- a second billing ledger;
- a second provider retry engine;
- arbitrary Agent SQL;
- unbounded graph mutation;
- trace-derived business state.

These boundaries are preserved for later nodes, beginning with NODE-34 Context Engine.

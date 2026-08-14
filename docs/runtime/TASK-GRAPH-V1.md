# LUMI Task Graph Runtime V1

> NODE-33 — Task Graph & Scheduler  
> Runtime contract: `TaskGraph:v1`  
> Depends on: NODE-10 Persistence, NODE-19 Queue/Event Runtime, NODE-20 Idempotency, NODE-27 Cost/Quota, NODE-32 Workflow/Recipe Engine  
> Next: NODE-34 Context Engine

## 1. Purpose

Task Graph is the project-level durable execution ledger for LUMI AI DESIGN OS.

It converts a compiled NODE-32 `TaskGraphTemplate` into persistent Task instances that can survive process restarts, wait for humans or providers, retry safely, run bounded parallel work, expose a product timeline, and support cooperative cancellation.

Task Graph is deliberately different from two adjacent concepts:

- **Recipe** defines the deterministic business skeleton and versioned provenance.
- **Task Graph** records durable project execution and scheduling state.
- **Deep Agent Todo** is an Agent-local reasoning/planning aid and is not the project execution source of truth.

The UI must query Task Graph state for project progress. It must not reconstruct business state from LangSmith traces or Agent Todo text.

## 2. Architectural boundary

```text
NODE-32 Recipe Engine
        |
        | CompiledRecipe + TaskGraphTemplate
        v
NODE-33 TaskGraph Instantiator
        |
        | immutable graph/task provenance
        v
TaskGraphService / Scheduler
        |
        +--> tasks + task_dependencies
        +--> task_graph_instances
        +--> task_attempts
        +--> NODE-19 outbox_events
        |
        +--> Agent Runtime / deterministic service / media worker / human wait
        |
        +--> NODE-20 logical side-effect identity
        +--> NODE-27 budget/quota reservation
```

NODE-33 does not grant model, tool, browser, filesystem, provider, or database authority to an Agent. It schedules already-authorized execution owners.

## 3. Source-of-truth tables

NODE-33 intentionally reuses the existing workflow ledger from `0002_workflow_platform_schema`:

- `tasks`
- `task_dependencies`
- `outbox_events`

It does **not** create a competing second Task table.

Migration `0015_task_graph_runtime` adds:

- `task_graph_instances`
- `task_attempts`
- TaskGraph-specific columns on `tasks`

The existing `tasks.type`, `owner_agent_key`, `input_json`, `output_json`, `budget_reserved`, attempt fields, timestamps and existing foreign keys remain compatible with earlier nodes.

## 4. Graph provenance

A TaskGraph instance freezes:

- `recipe_id`
- `recipe_version`
- Recipe definition hash
- Recipe provenance hash
- TaskGraphTemplate hash
- final TaskGraph provenance hash
- organization/project/agent-run IDs
- recipe budget upper bound
- task count

A process restart reloads the same graph identity rather than recompiling a newer Recipe alias.

This prevents a long-running project from silently changing behavior because an Agent, Skill, Model policy or Recipe release moved after the run started.

## 5. Deterministic identity

Task IDs are derived deterministically from the Graph identity and Task key for compiled Recipe tasks.

Dynamic child tasks use a deterministic identity derived from:

```text
graph_id + parent_task_id + dynamic child key
```

This gives stable replay/debug identity while the database still enforces:

```text
UNIQUE(task_graph_id, task_key)
```

## 6. Task states

V1 Task states are:

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

Terminal states:

```text
SUCCEEDED
FAILED_FINAL
CANCELLED
SKIPPED
```

WAITING states are durable. A process can restart while a Task waits for approval, user input or an external asynchronous provider.

## 7. Graph states

Graph state is derived from durable Task state rather than Agent narration.

The reference runtime supports:

```text
PENDING
RUNNING
SUCCEEDED
FAILED_FINAL
CANCELLED
```

A graph reaches a terminal state only when its durable Task ledger permits that conclusion.

## 8. State-version CAS

Every NODE-33 Task has an independent `state_version` in addition to the older generic row version.

State mutations use compare-and-set semantics:

```text
WHERE id = :task_id
  AND state_version = :expected
  AND status = :expected_status

SET state_version = state_version + 1
```

A stale scheduler/worker therefore cannot overwrite a newer state transition.

## 9. Readiness

A Task becomes `READY` only after the pure runtime has established that its business conditions are satisfied.

Readiness considers:

- dependency terminal states;
- join policy;
- safe condition expression;
- graph cancellation;
- retry delay;
- attempt budget;
- Task/parallel concurrency constraints;
- upstream failure semantics.

The database claim query does not reimplement Recipe business logic. It only claims rows already marked `READY`.

This keeps one definition of join/condition behavior.

## 10. Join policies

NODE-33 supports bounded join policies compiled by NODE-32:

### ALL

All required dependencies must satisfy the join.

### ANY

At least one dependency must succeed/satisfy the join. Once all dependencies are terminal and none satisfy it, the downstream Task cannot become ready.

### MIN_SUCCESS

A configured minimum number of dependencies must succeed. The runtime can decide early when the threshold is reached or can mark the downstream branch unsatisfied once the threshold becomes impossible.

## 11. Safe conditions

Task conditions reuse NODE-32's restricted expression evaluator.

Allowed expression roots are bounded data contexts such as:

```text
inputs
project
steps
run
```

Arbitrary Python execution, function calls, subprocesses, SQL, provider SDKs and network access are not available to conditions.

A false condition produces deterministic branch skipping rather than executing an Agent to "decide" whether to ignore the step.

## 12. Scheduler claim algorithm

The PostgreSQL scheduler uses a transaction-local loop:

```text
SELECT one READY candidate
FOR UPDATE SKIP LOCKED
LIMIT 1

-> verify graph active
-> verify retry_not_before
-> verify attempt capacity
-> verify concurrency group capacity
-> CAS READY -> RUNNING
-> create task_attempts row
-> create task.started outbox event
-> repeat up to requested bounded batch size
```

Using `LIMIT 1` inside the transaction is intentional. The second selection sees the first Task already marked `RUNNING`, so a batch cannot accidentally over-claim a concurrency group.

Multiple scheduler replicas can race without claiming the same row because PostgreSQL row locks and `SKIP LOCKED` provide the serialization boundary.

## 13. Lease and heartbeat

A claimed Task records:

- `lease_owner`
- `lease_expires_at`
- `heartbeat_at`
- incremented attempt number

A worker may heartbeat only while:

```text
status == RUNNING
lease_owner == worker
lease_expires_at >= now
```

Completion uses the same lease ownership checks.

A stale worker therefore cannot finish a Task after another recovery path has taken ownership.

## 14. Lease expiry is not paid-retry permission

A crashed worker creates ambiguity for external paid side effects.

NODE-33 therefore treats lease expiry as:

```text
FAILED_RETRYABLE
provider_reconciliation_required = true
failure = lease_expired
```

It does **not** assume that the external request failed.

Before paid work is repeated, execution must flow through NODE-20 reconciliation/idempotency semantics.

## 15. Logical operation identity

This is a critical cross-node invariant.

The logical idempotency identity is:

```text
task:<graph_id>:<task_id>
```

It does not contain the attempt number.

Example:

```text
attempt 1 -> task:GRAPH:TASK
attempt 2 -> task:GRAPH:TASK
attempt 3 -> task:GRAPH:TASK
```

`attempt_number` records execution history only.

This allows NODE-20 to classify a repeated attempt as replay/reconcile/retry-safe for the same logical side effect instead of treating each attempt as a new paid operation.

## 16. Attempt ledger

`task_attempts` records:

- Task/Graph/organization identity
- monotonically increasing attempt number
- stable logical operation key
- execution status
- error category
- result reference
- cost amount
- start/completion timestamps

`UNIQUE(task_id, attempt_number)` prevents duplicate attempt numbers.

The logical operation key is intentionally **not unique**, because multiple execution attempts belong to one logical idempotent operation.

Attempt rows are non-deletable by the runtime application role. An active attempt may be updated from `RUNNING` to its terminal/wait/retry state; store SQL requires `status = 'RUNNING'` for that lifecycle transition.

## 17. Retry

Retry flow is:

```text
RUNNING
  -> FAILED_RETRYABLE
  -> READY with retry_not_before
  -> RUNNING (new attempt_number, same logical_operation_key)
```

The Task never becomes a new logical Task during retry.

`max_attempts` is bounded. Once retry is not allowed, failure becomes final.

## 18. WAIT and resume

Durable wait states:

```text
WAITING_APPROVAL
WAITING_INPUT
WAITING_EXTERNAL
```

Entering WAIT clears the worker lease and finishes the active execution attempt.

A resume requires an explicit resume reference, for example:

```text
approval://...
input://...
provider-result://...
```

Resume transitions the same Task back to `READY`; it does not create a replacement Task.

## 19. Cancellation

Graph cancellation has two policies in one operation:

- non-running Tasks are cancelled immediately;
- RUNNING Tasks receive `cancellation_requested_at` and must cooperatively acknowledge cancellation.

This avoids killing an in-flight external side effect without knowing its provider state.

Completed Artifacts are not deleted by Task cancellation. Cancellation stops future execution; Artifact retention/version policy remains owned by the Artifact subsystem.

## 20. Parallel concurrency

NODE-32 fan-out metadata becomes:

- `concurrency_group`
- `concurrency_limit`

The durable scheduler counts `RUNNING` Tasks in the same Graph/group before each claim.

A configured group limit is therefore enforced across multiple scheduler processes, not only inside one Python process.

## 21. Parallel budget boundary

NODE-32 computes bounded parallel structure. NODE-33 carries Task/Recipe budget upper bounds; NODE-27 remains the authoritative cost/quota reservation service.

The intended execution ordering is:

```text
fan-out upper bound known
-> reserve safe upper bound / validate budget
-> mark eligible Tasks READY
-> claim Tasks
-> execute side effects through NODE-20/NODE-22/NODE-25
```

TaskGraph scheduling does not create a second billing ledger.

## 22. Dynamic Task expansion

Agents may propose dynamic child work only through the TaskGraph boundary.

V1 limits:

```text
max dynamic depth: 4
max children per parent: 32
```

Additional rules:

- parent must be RUNNING;
- parent must explicitly allow dynamic children;
- child budget cannot exceed parent budget;
- child concurrency cannot widen parent concurrency;
- child dynamic-child scope cannot widen parent scope;
- Task count is atomically increased;
- dynamic Task identity is deterministic;
- a child cannot silently become a new authority boundary.

These rules prevent unbounded self-expansion by an Agent.

## 23. Progress

Task progress is only stored when a real denominator exists:

```text
progress_current
progress_total
```

Progress is monotonic for a running attempt.

Project-level progress is based on terminal durable Tasks, not token count, trace span count or guessed Agent percentages.

The product must not display fabricated progress such as "87%" when no meaningful denominator exists.

## 24. Events and NODE-19 outbox

NODE-33 writes events through the existing NODE-19 `outbox_events` schema:

```text
event_name
aggregate_type
aggregate_id
schema_version
payload_json
publish_attempts
```

Key Task events include:

```text
task.ready
task.started
task.waiting
task.progress
task.retry_scheduled
task.succeeded
task.failed
task.cancel_requested
task.cancelled
task.dynamic_created
```

Outbox writes occur in the same database transaction as the state mutation where implemented, preventing state/event split-brain.

## 25. Canonical Task columns

NODE-33 preserves legacy columns while adding exact execution metadata.

Examples:

```text
type                  # existing canonical Task type
owner_agent_key       # existing compatibility owner for Agent tasks
owner_key             # exact generic owner, e.g. AGENT:id@version or service owner
budget_reserved       # existing accounting compatibility
budget_limit_usd      # Task upper-bound policy
input_json/output_json
metadata_json
output_schema
state_version
lease_owner/lease_expires_at/heartbeat_at
retry_not_before
wait_reason/external_ref
cancellation_requested_at
progress_current/progress_total
dynamic_depth/dynamic_child_limit
concurrency_group/concurrency_limit
```

The Postgres store is contract-tested against these canonical names to prevent schema drift.

## 26. ORM metadata alignment

The API ORM exposes:

- extended `Task`
- `TaskGraphInstance`
- `TaskAttemptRecord`

`lumi_api.persistence.models` imports the new models so Alembic metadata sees the NODE-33 schema.

This is required for `alembic check` to be meaningful.

## 27. Restart and recovery

`PostgresTaskGraphStore` provides durable read/write primitives for:

- graph load
- Task list with dependencies
- attempt list
- direct Timeline query
- claim
- heartbeat
- ready CAS
- running completion/wait/failure
- waiting resume
- retry scheduling
- lease reclaim
- cancellation

A scheduler process may therefore restart and reconstruct runnable state from PostgreSQL without relying on in-memory Agent state.

## 28. Timeline query

The product Timeline is directly queryable from Tasks and Attempts.

It includes fields such as:

- Task key / Recipe step
- Task type / owner
- state
- priority
- progress
- attempt count
- started / finished timestamps
- wait reason / external reference
- persisted attempt count

LangSmith remains an observability/trace system, not the business Timeline database.

## 29. Security boundary

The TaskGraph runtime package intentionally imports no:

- asyncpg
- SQLAlchemy
- provider SDK
- browser/network SDK
- Docker/subprocess authority

The Postgres adapter accepts an injected connection protocol.

Database credentials stay in the API/worker process configuration, not in Agent definitions or Recipe files.

## 30. Validation layers

NODE-33 has three intended CI gates.

### task-graph-contract

- Python compile
- NODE-32 contract revalidation
- NODE-33 static contract
- dependency-light TaskGraph unit tests
- Recipe → TaskGraph deterministic integration

### task-graph-quality

- frozen workspace install
- pytest
- Ruff
- Pyright

### task-graph-postgres

- start repository PostgreSQL infrastructure
- migrate to head
- Alembic ORM drift check
- deterministic seed
- concurrent scheduler Postgres integration
- downgrade/upgrade smoke

## 31. PostgreSQL acceptance race

The dedicated integration isolates the `product-visuals` render fan-out and launches multiple scheduler claimers concurrently.

Acceptance requires:

- all eligible render Tasks claimed exactly once;
- no duplicate Task IDs;
- concurrency group upper bound respected;
- retry creates attempt 2 for the same Task;
- both attempts share the same logical operation key;
- Timeline is queryable;
- Task events exist in canonical outbox rows;
- `lumi_app` cannot delete Task attempt history.

## 32. Non-goals

NODE-33 does not implement:

- arbitrary Agent-created SQL;
- a second provider/model retry system;
- a second cost ledger;
- prompt/context assembly;
- vector retrieval;
- LangSmith-as-database;
- unbounded DAG mutation;
- process-local-only scheduling as the production source of truth.

Context assembly and retrieval are introduced in NODE-34.

## 33. Operational invariants

The following invariants are release blocking:

1. Recipe provenance is frozen at Graph instantiation.
2. A READY Task can be claimed by at most one active worker lease.
3. Scheduler replicas use `FOR UPDATE SKIP LOCKED` plus state-version CAS.
4. A stale lease cannot authorize blind repeat of a paid side effect.
5. Retry reuses the same logical operation key.
6. Attempt number is history, not idempotency identity.
7. Dependency/condition business rules are evaluated before `READY`.
8. Dynamic expansion cannot widen budget/concurrency/child scope.
9. Cancellation is cooperative for RUNNING work.
10. Task/Attempt/Outbox persistence uses the canonical existing database schema.
11. Project Timeline is queryable without parsing traces.
12. No NODE-33 status is marked complete until the required execution gates have actually run green.

## 34. Handoff to NODE-34

NODE-34 Context Engine may consume TaskGraph identity, Task outputs and provenance to construct bounded Agent context.

It must not mutate Task history or bypass TaskGraph scheduling. Context is execution input; TaskGraph remains the durable project execution ledger.

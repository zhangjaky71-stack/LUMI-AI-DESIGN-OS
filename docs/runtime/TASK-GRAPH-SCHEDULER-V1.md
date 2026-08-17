# LUMI Task Graph & Scheduler V1

> NODE-33 — Task Graph & Scheduler  
> Current stacked base: NODE-32 Context Compiler V1  
> Runtime package: `lumi_agent_runtime.task_graph`

## 1. Purpose

NODE-33 is the durable-execution contract between the LangGraph control plane and bounded task executors.
It converts one immutable task DAG into recoverable task state with deterministic IDs, readiness rules,
claim leases, retries, cancellation, budget guards and provenance-safe execution pins.

The boundaries are explicit:

- NODE-28 owns the top-level LangGraph run/control state machine.
- NODE-29 owns one bounded Deep Agent task execution.
- NODE-30/31 resolve exact Agent and Skill versions.
- NODE-32 freezes the exact Context Bundle consumed by a task.
- NODE-33 owns task-DAG lifecycle and scheduling state.

TaskGraph state is business execution state. It must not be reconstructed from LangSmith traces or model text.

## 2. Immutable definition

`TaskGraphDefinition` freezes:

- `graph_key` and exact graph version;
- organization/project/agent-run identity;
- immutable `TaskDefinition` rows;
- graph budget limit;
- graph max parallelism;
- failure mode;
- provenance refs and safe metadata.

The definition is canonical-JSON hashed with SHA-256. The graph ID is deterministic from the run identity and
definition hash. Repeating `ensure_graph()` with the same definition is idempotent. Reusing the same run with a
different definition fails closed with `TASK_GRAPH_RUN_DEFINITION_CONFLICT`.

Task IDs are deterministic UUIDv5 values derived from the immutable graph ID plus `task_key`.

## 3. DAG invariants

Publication rejects:

- duplicate task keys;
- missing dependency keys;
- self-dependencies;
- cycles;
- inconsistent limits for the same concurrency group;
- invalid task or graph budget values;
- more than 2048 tasks in one V1 graph.

The V1 DAG is immutable after instantiation. Dynamic sub-agent work remains inside NODE-29 delegation unless a
future governed graph-publication flow emits a new exact graph definition. This keeps replay identity stable.

## 4. Exact Agent and Context pins

`TaskKind.AGENTIC` requires both:

```text
agent_ref = <agent-id>@<exact-version>
context_bundle_ref = context-bundle://...
```

Aliases are not accepted at the TaskGraph boundary. NODE-33 never resolves a newer Agent or Context version during
retry/replay.

`ScheduledAgentTaskRequestResolver` structurally implements NODE-29 `AgentTaskRequestResolver`. It accepts only one
claimed `RUNNING` AGENTIC task selected by `current_task_ids`, validates organization/project/run/task identity,
checks the root Agent ID, and returns the exact pinned `DeepAgentTaskRequest`.

## 5. Task states

```text
pending
ready
running
waiting_user
waiting_external
succeeded
failed_retryable
failed_final
cancelled
skipped
```

Terminal task states are `succeeded`, `failed_final`, `cancelled`, and `skipped`.

Graph states are:

```text
running
paused
waiting
failure_draining
cancel_requested
succeeded
failed_final
cancelled
```

`failure_draining` and `cancel_requested` are intentionally non-terminal. They preserve the fact that an in-flight
provider or side-effect task may still own a valid lease and must be cooperatively drained/reconciled.

## 6. Readiness and join rules

V1 supports:

- `ALL_SUCCESS`
- `ALL_TERMINAL`
- `ANY_SUCCESS`

A pending task becomes READY only after the join rule is satisfied. If a join becomes impossible, the task becomes
SKIPPED with `TASK_UPSTREAM_UNSATISFIED` rather than remaining pending forever.

Retryable tasks become READY only after `retry_not_before`.

## 7. Claim, priority and concurrency

`claim_ready()` is a bounded scheduling transaction. Candidate order is deterministic:

```text
priority DESC
then task_key ASC
```

Claims are constrained by:

- graph `max_parallelism`;
- per-task attempt capacity;
- optional concurrency group and group limit;
- cancellation/failure-draining state;
- graph and task budget guards.

A production store must implement the same transaction boundary with durable locking/CAS semantics. The bundled
`InMemoryTaskGraphStore` is the deterministic reference adapter for tests and local execution only.

## 8. Lease fencing

Every claim creates:

- `lease_owner`;
- unique `lease_token`;
- `lease_expires_at`;
- `heartbeat_at`;
- monotonically increasing `attempt_count`.

Heartbeat, completion, failure, and suspension require the current owner and exact lease token. A stale worker cannot
complete a task after ownership moved.

Lease expiry never proves an external paid operation failed. Expired work is marked with
`provider_reconciliation_required=true`, and the task becomes retryable or final based on attempt capacity.

## 9. Stable logical operation key

The idempotency identity is stable across retries:

```text
task:<graph_id>:<task_id>
```

Attempt number and lease token are not part of that logical operation key. Side-effect executors must pass the stable
key into the system idempotency/reconciliation boundary. Lease token is a fencing credential, not an idempotency key.

## 10. Retry

`RetryPolicy` freezes:

- maximum attempts;
- deterministic base delay;
- deterministic maximum delay;
- backoff multiplier.

No random jitter is included in the canonical retry calculation, preserving replay determinism. Infrastructure may
delay dispatch later than `retry_not_before`, but never earlier.

Transition:

```text
running
  -> failed_retryable
  -> ready (after retry_not_before)
  -> running (new lease, same task/logical operation identity)
```

## 11. Failure propagation

Graph `FailureMode` is either:

- `FAIL_FAST`: one final task failure enters `failure_draining`, skips/cancels unstarted work, requests cancellation
  on running tasks, then finishes `failed_final` after active leases drain;
- `CONTINUE`: independent work may continue, but joins that can no longer succeed are skipped. The graph finishes
  failed if any task is final-failed.

No final failure is silently converted to success.

## 12. Pause, resume and cancellation

Pause is a scheduling pause: no new task may be claimed, while already-running leases may finish.

Resume returns the graph to runnable evaluation.

Cancellation is cooperative:

- pending/ready/retry/waiting work becomes cancelled immediately;
- running tasks receive `cancellation_requested_at` but keep their current lease;
- the graph becomes `cancelled` only after active leases drain.

This avoids pretending in-flight provider side effects disappeared.

## 13. Wait states

A running task may suspend into `waiting_user` or `waiting_external`. Suspension closes the active attempt and clears
the lease. `resolve_wait()` then either succeeds or final-fails the same task.

Wait references are URI-like provenance references and are never arbitrary inline binary payloads.

## 14. Budget boundary

NODE-33 records graph/task budget ceilings and actual attempt cost, and stops new scheduling once the graph ceiling is
exhausted. It is not a replacement for the authoritative provider-cost reservation/ledger boundary.

Concurrent paid operations must still reserve provider cost before provider acceptance. NODE-33 therefore prevents
continued scheduling after observed exhaustion, while the system cost/quota layer prevents concurrent oversubscription.

## 15. NODE-28 adapter

`ControlPlaneTaskGraphAdapter` structurally satisfies the existing NODE-28 `TaskGraphPort`:

```python
await ensure_task_graph(state) -> list[str]
await next_route(state) -> str
```

Routes are the frozen NODE-28 route vocabulary:

```text
deterministic
agentic
side_effect
wait_external
approval
done
```

Route inspection never claims a task as a hidden side effect. Worker/executor composition must explicitly claim and
later complete/fail/suspend through `TaskGraphScheduler`.

## 16. Safe events

TaskGraph events carry only safe structured payloads. Keys associated with private reasoning (`reasoning`,
`chain_of_thought`, `scratchpad`, raw prompts/messages/tool output) are rejected.

Events include stable logical operation identity but never private model reasoning.

## 17. Transaction store contract

`TaskGraphStore` requires an atomic graph transaction. Within that boundary a scheduler can:

- read immutable definition;
- load graph/tasks;
- CAS graph/task state versions;
- append/finish attempt ledger entries;
- append safe task/graph events.

A production SQL implementation must provide equivalent row-locking/fencing semantics across scheduler replicas.
The in-memory adapter serializes the same boundary with an async lock for deterministic contract tests.

## 18. Acceptance boundary

NODE-33 V1 considers the scheduling contract implemented when local contract tests cover DAG validation,
idempotent instantiation, readiness, priority/concurrency, retry, lease fencing, reclaim, failure modes, budget,
pause/resume/cancel, waits, NODE-28 routing, safe events, and NODE-29 exact-pin request resolution.

Production completion still requires the durable multi-replica store and worker composition gaps in the NODE-33 gap
ledger, plus an actual hosted CI runner execution.

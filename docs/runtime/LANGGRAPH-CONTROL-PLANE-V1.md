# LUMI LangGraph Control Plane V1

Status: `IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

Owner node: `NODE-28 — LangGraph Control Plane`

## 1. Purpose

NODE-28 is the durable orchestration boundary for one LUMI AgentRun. It decides **what
runs next and when execution yields**, while delegating specialist intelligence and side
effects to ports owned by later or lower-level nodes.

It is intentionally not:

- the Deep Agents specialist runtime (NODE-29),
- the Workflow Recipe Engine (NODE-32),
- the Task Graph domain model (NODE-33),
- the provider/model gateway (NODE-22),
- the generic tool gateway (NODE-25),
- the queue runtime (NODE-19), or
- the idempotency source of truth (NODE-20).

## 2. Hard invariants

1. One AgentRun owns one stable LangGraph `thread_id`.
2. Every durable run pins `graph_key`, `graph_version`, and `code_git_sha`.
3. A graph version cannot silently change its content identity.
4. LangGraph checkpoint state stores IDs, references, bounded control facts, and progress;
   it does not replace PostgreSQL business entities.
5. Binary payloads and inline `data:` blobs are forbidden from Graph State.
6. Unknown Graph State keys are rejected.
7. Production execution must use a durable checkpointer; `InMemorySaver` is testing-only.
8. PostgreSQL graph control rows are tenant-scoped with RLS.
9. Resume is fenced by tenant/project/thread + graph identity + interrupt id +
   `resume_version` + checkpoint CAS.
10. The interrupted node may restart from its beginning. Any side effect before an
    interrupt must therefore be idempotent.
11. Long-running provider/media work checkpoints and yields; it is resumed by an
    external completion signal rather than polling inside the graph.
12. UI/event payloads are structured progress only. Prompts, chain-of-thought,
    scratchpads, raw provider responses and raw tool outputs are forbidden.
13. Cancellation must cancel pending work and release reservations before the control
    projection becomes cancelled.
14. Same operation retries must replay; operation identity must not depend on a checkpoint
    id that advances after success.

## 3. Main graph

Canonical identity:

- `graph_key = lumi.main`
- `graph_version = 1.0.0`
- `state_schema_version = 1`

High-level flow:

```text
START
  -> validate_run
  -> load_project_snapshot
  -> select_or_load_recipe
  -> ensure_task_graph
  -> route_ready_tasks
       -> deterministic_task
       -> deep_agent_task
       -> side_effect_task
       -> media_job_wait
       -> approval_interrupt
       -> collect_results
  -> quality_gate
       -> repair -> route_ready_tasks
       -> approval -> approval_interrupt
       -> finalize
  -> END
```

### Node categories

| Category | Meaning | Contract |
|---|---|---|
| `deterministic` | Repeatable orchestration/computation | no uncontrolled external side effect |
| `agentic` | Specialist reasoning | implementation delegated to NODE-29 |
| `side_effect` | External/durable write | must enter through idempotent port |
| `wait_external` | Long-running external work | submit idempotently, interrupt, resume on completion |
| `human_interrupt` | Approval/input gate | interrupt before irreversible work |

## 4. Graph State

`LumiRunState` currently carries:

- run / organization / project / optional task ids,
- brief version,
- selected recipe version,
- current task ids,
- approval id,
- public run status,
- context references,
- artifact references,
- decimal budget remaining as a string,
- structured errors,
- graph identity,
- routing marker,
- external job id,
- bounded repair counters.

State safety rules:

- max serialized state: 1 MiB,
- JSON-safe values only,
- non-finite numbers rejected,
- bytes/memoryview rejected,
- inline `data:` values rejected,
- undeclared keys rejected,
- budget must be a finite non-negative decimal string.

Large assets, documents, prompts, provider bodies, visual files and business entities stay
in their owner systems and are referenced by ids/URIs only.

## 5. Checkpoint architecture

There are two persistence responsibilities and they must not be confused.

### 5.1 LangGraph checkpoint store

Owns native LangGraph checkpoints, pending writes, interrupt state and thread history.

- tests: `InMemorySaver`,
- production target: async PostgreSQL saver,
- production saver package is lazy-loaded and currently an explicit packaging gap,
- runtime requires strict msgpack mode before opening the production saver,
- setup/schema creation is an admin/migration concern, not a request-path concern.

### 5.2 LUMI run-control projection

`agent_run_control` is a small application projection used for authorization, query,
version fencing and operational recovery. It stores:

- tenant/project/run/task identity,
- graph identity and definition hash,
- thread id,
- public control status,
- latest checkpoint id/namespace,
- bounded public state values,
- next node names,
- active interrupt descriptors,
- monotonic `resume_version`,
- error code,
- optimistic row version.

It does **not** attempt to recreate LangGraph checkpoint internals.

## 6. Graph definition provenance

`agent_graph_definitions` is global runtime metadata, read-only to the normal app role.
A published graph version records:

- graph key/version,
- agent config version,
- source code git SHA,
- state schema version,
- canonical content hash,
- enabled flag,
- bounded metadata.

`agent_run_control` has a composite FK to a published graph definition. A PostgreSQL
trigger additionally rejects control rows when:

- the definition is missing,
- the definition is disabled,
- the definition hash differs, or
- the code git SHA differs.

The Python registry applies the same fail-closed principle before executing a graph.

## 7. Start semantics

`StartRunCommand` contains the immutable business binding needed to start a thread.
The control plane:

1. creates a semantic operation hash from caller intent,
2. enters `OperationGuard`,
3. checks whether a control projection already exists,
4. verifies any replay has the same tenant/project/thread/graph binding,
5. invokes the compiled graph with the stable thread id,
6. reads the checkpointed state,
7. stores the LUMI projection,
8. emits safe lifecycle events.

Start retries with the same operation must not execute the graph twice.

## 8. Interrupt and resume semantics

`ResumeRunCommand` carries:

- tenant/project/run identity,
- stable thread id,
- operation id,
- `resume_version`,
- interrupt id,
- resume kind,
- JSON-safe resume value,
- expected graph key/version/code SHA.

Resume verifies:

1. tenant-scoped run exists,
2. project/thread binding matches,
3. graph identity matches,
4. run is not already terminal unless the operation is replaying,
5. resume version is current,
6. interrupt id is active and resumable,
7. application approval/input policy authorizes the value,
8. LangGraph resumes the same thread with `Command(resume=...)`,
9. the LUMI projection advances with checkpoint + resume-version CAS.

The operation request hash is based only on the resume command. It intentionally excludes
the current checkpoint id so a successful request can be retried after the checkpoint has
advanced and still replay the same operation result.

## 9. Human approval

`approval_interrupt` emits JSON-only interrupt data. It never places an external side
effect before the interrupt. V1 supports structured approve/reject actions through the
port contract; production approval identity/token/version binding remains an explicit gap.

## 10. Long-running external jobs

`media_job_wait` uses this contract:

1. `ExternalJobPort.submit_idempotent(state)` returns a stable external job id,
2. graph interrupts with that job id,
3. no polling loop remains active,
4. a completion event later resumes the same thread,
5. the interrupted node starts again,
6. `submit_idempotent` may therefore be called again but must resolve the same logical job,
7. completed output is collected once and stored as refs.

The NODE-19 `job.completed -> resume` production wake adapter is not yet composed.

## 11. Side-effect boundary

The main graph never imports provider SDKs and never directly calls provider HTTP APIs.
Side effects use `SideEffectTaskPort.execute_idempotent` and must ultimately compose with
NODE-20 / NODE-22 / NODE-25 as appropriate.

The NODE-28 production `OperationGuard` binding to NODE-20 is an explicit gap. The tests
use an in-memory reference guard to prove orchestration semantics without claiming the
production transaction composition is complete.

## 12. Cancellation

The current control-plane cancellation path is cooperative and safe-point oriented:

1. locate the run in tenant scope,
2. enter operation guard,
3. return immediately if already terminal,
4. cancel pending queue/provider work through `CancellationPort`,
5. release reservations/budget occupancy,
6. CAS the run-control projection to cancelled,
7. emit `run.cancelled`.

A future worker may persist `cancel_requested` before reaching its safe point; both
`agent_runs` and `agent_run_control` schemas accept that state.

## 13. Safe events

Allowed event types:

- `run.started`
- `node.started`
- `agent.status`
- `agent.delta`
- `tool.call`
- `task.progress`
- `approval.required`
- `artifact.created`
- `run.completed`
- `run.cancelled`
- `run.waiting_external`

Safe event payloads reject private-reasoning keys recursively, including prompt, messages,
reasoning, chain-of-thought, scratchpad, raw response and raw tool output fields.

The UI may show what node is active, what safe tool/action category is running, public
progress, artifact creation and approval requirements. It may not show hidden reasoning.

## 14. API surface

Authenticated command endpoints:

- `POST /api/v1/agent-runs/{agent_run_id}/resume`
- `POST /api/v1/agent-runs/{agent_run_id}/cancel`

There are deliberately no public endpoints to write arbitrary checkpoint data or mutate
raw Graph State. Existing API auth maps these POST requests to `project.write`.

The runtime service dependency is fail-closed with HTTP 503 until production composition
is installed.

## 15. PostgreSQL schema

Migration: `20260816_0010`, stacked on `20260816_0009`.

Changes:

- widens `agent_runs.thread_id` to 255,
- widens graph/config version columns to 100,
- adds `graph_key` and `code_git_sha`,
- adds `waiting_external` to AgentRun status,
- adds `agent_graph_definitions`,
- adds `agent_run_control`,
- enables tenant RLS on run-control,
- normal app role may read definitions and read/insert/update own control rows,
- normal app role cannot delete control history or mutate graph definitions,
- same-tenant reference trigger protects run/project/task relations,
- graph-definition trigger protects version/hash/code provenance.

Downgrade is allowed only before durable NODE-28 control state exists. Once a run-control
row exists, downgrade fails rather than destroying resumability evidence.

## 16. Tests and acceptance gates

Authored tests cover:

- complete deterministic mock run,
- start operation replay,
- human interrupt and resume,
- stale resume version,
- same resume operation replay after checkpoint advancement,
- graph version drift,
- external job checkpoint/wake semantics,
- interruption node re-execution with stable job identity,
- cancellation and reservation release callbacks,
- binary/data URI/unknown state rejection,
- private reasoning event rejection,
- production checkpointer fail-closed policy,
- command-only API surface,
- PostgreSQL RLS and tenant-scoped store behavior,
- checkpoint/resume-version CAS,
- AgentRun status projection,
- safe migration downgrade/reapply,
- lossy downgrade refusal,
- static architecture validation,
- six generated JSON Schemas.

No hosted PASS is claimed until a GitHub-hosted runner is actually allocated and executes
the workflow.

## 17. Explicit open gaps

See `reports/nodes/NODE-28/gap-ledger.json`. The eight tracked gaps are:

1. `GRAPH-CHECKPOINT-PACKAGE-001`
2. `GRAPH-STORE-PACKAGE-002`
3. `GRAPH-COMPOSITION-003`
4. `GRAPH-IDEMPOTENCY-004`
5. `GRAPH-APPROVAL-005`
6. `GRAPH-JOB-WAKE-006`
7. `GRAPH-OBS-007`
8. `GRAPH-CI-008`

These gaps do not block later source nodes that can build against the ports and durable
contracts already defined here.

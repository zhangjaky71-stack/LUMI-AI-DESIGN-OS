# LUMI LangGraph Control Plane V1

> NODE: 28  
> Phase: 4 — Agent Runtime / Control Plane  
> Status: IMPLEMENTED / VALIDATING  
> Depends on: NODE-16/17 identity + approval surfaces, NODE-20 idempotency, NODE-22 Model Gateway, NODE-25 Tool Gateway, NODE-27 budget/cost foundation

---

## 1. Purpose

NODE-28 turns LangGraph from a graph library into a controlled LUMI runtime.

The control plane owns:

- immutable graph/version selection;
- AgentRun/thread binding;
- durable checkpoint requirements;
- start/resume/cancel command idempotency;
- checkpoint compare-and-swap;
- interrupt normalization;
- LUMI Approval/Input authorization before resume;
- operational lifecycle events;
- restart-safe graph reconstruction.

LangGraph owns:

- node/edge execution;
- persisted graph state checkpoints;
- `interrupt()` pause points;
- `Command(resume=...)` continuation;
- checkpoint history semantics.

The division is intentional. LangGraph is not allowed to become a second tenant, permission, approval, billing or side-effect correctness plane.

---

## 2. Architectural placement

```text
API / Agent caller
        ↓
GraphControlPlaneClient
        ↓
LangGraphControlPlane
        ├─ GraphRegistry
        ├─ NODE-20 ControlPlaneOperationGuard
        ├─ GraphRunStore / checkpoint CAS
        ├─ PolicyResumeAuthorizer
        └─ GraphEventSink
        ↓
DurableLangGraphExecutor
        ↓
exact compiled graph version
        ↓
LangGraph durable checkpointer
```

Inside graph nodes:

```text
model work   → NODE-22 Model Gateway → NODE-27 cost/budget
external tool → NODE-25 Tool Gateway → NODE-20 side-effect guard
sandbox work → NODE-21 Sandbox
assets       → NODE-18 Asset/Object Storage
```

Forbidden:

```text
Agent → arbitrary compiled graph
Agent → checkpointer
Agent → Command(resume=client_value)
Graph node → provider SDK directly
Graph node → arbitrary network/DB credentials
Graph node → unrestricted host shell
```

---

## 3. Immutable GraphDefinition

Every production graph is identified by:

```text
graph_key
graph_version
agent_config_version
state_schema_version
input_schema_version
output_schema_version
interrupt_policy_version
content_hash
```

A GraphDefinition version is immutable.

Registering the same:

```text
graph_key@graph_version
```

with different content is a version conflict.

Changing graph structure, state contract, agent configuration assumptions or interrupt behavior requires a new graph version unless the immutable definition hash remains identical.

### Why exact versions matter

A suspended AgentRun may resume hours or days later.

It must resume against the exact graph/config semantics that produced its checkpoint, not whatever deployment happens to be called “latest” at resume time.

---

## 4. Durable graph catalog

Migration `0012_langgraph_control_plane` adds:

```text
agent_graph_definitions
```

The table records deployed immutable definition provenance.

Runtime `lumi_app` receives SELECT only.

Installation/update of the catalog uses an admin/migration path. The P0 `PostgresGraphDefinitionCatalog.install()` permits:

- first installation of a version;
- toggling `enabled` when immutable content is identical;
- no content/hash/schema/config mutation under the same version.

Before serving production traffic, the composition root should verify code-deployed GraphDefinition hashes against the durable catalog.

---

## 5. AgentRun/thread binding

One AgentRun binds to one stable LangGraph `thread_id`.

NODE-28 persists the control binding in:

```text
agent_run_control
```

Important fields:

```text
agent_run_id
organization_id
project_id
task_id?
graph_key
graph_version
agent_config_version
graph_definition_hash
thread_id
control_status
checkpoint_id
checkpoint_namespace
state_values_json
next_nodes_json
interrupts_json
error_code
version
```

Uniqueness:

```text
organization_id + thread_id
```

A start replay with a different tenant/project/thread/graph/config/hash is rejected.

---

## 6. LangGraph checkpoint is execution truth

`agent_run_control` does **not** replace the LangGraph checkpointer.

LangGraph checkpoint storage remains the source of truth for durable graph execution.

The LUMI control row stores:

- exact run binding;
- checkpoint pointer;
- control status;
- normalized interrupts;
- a JSON-compatible snapshot copy used for idempotent control responses/audit.

Production graphs must be compiled with a checkpointer. `DurableCompiledGraphRegistry.register()` fails closed if a compiled graph has no checkpointer.

---

## 7. Production PostgreSQL checkpointer

NODE-28 provides:

```text
open_postgres_checkpointer(connection_string, allow_setup=False)
```

It loads the official asynchronous PostgreSQL LangGraph saver.

### Deployment/admin

Schema initialization may run with:

```text
allow_setup=True
```

and migration/admin credentials.

### Runtime

Runtime must open an already initialized checkpoint schema with:

```text
allow_setup=False
```

Runtime should not receive schema-mutation authority merely because LangGraph needs persistence.

The checkpoint DSN remains in the trusted composition root and is not copied into graph state, events or interrupt payloads.

---

## 8. Start command

Start request contains:

```text
organization_id
project_id
agent_run_id
task_id?
operation_id
graph_key
graph_version
agent_config_version
thread_id
input
trace_id?
```

Flow:

```text
resolve exact immutable GraphDefinition
        ↓
NODE-20-compatible operation guard
        ↓
bind AgentRun/thread/definition
        ↓
LangGraph ainvoke(input, thread_id)
        ↓
read checkpoint state
        ↓
persist control snapshot
        ↓
emit lifecycle events
```

The same control operation replay returns the original result and does not run the graph a second time.

---

## 9. Resume command

Resume is deliberately stricter than a raw LangGraph call.

Flow:

```text
load AgentRun control state
        ↓
require status=interrupted
        ↓
require exact interrupt_id
        ↓
NODE-20-compatible operation guard
        ↓
re-read fresh control state
        ↓
PolicyResumeAuthorizer
        ↓
verify authorization bound to current interrupt
        ↓
Durable thread→graph version binding
        ↓
Command(resume=normalized_authorized_value)
        ↓
read new checkpoint
        ↓
checkpoint CAS persist
```

The client-provided `request.value` is never passed directly to `Command(resume=...)` by the control plane.

---

## 10. Approval semantics

LangGraph `interrupt()` is a pause mechanism. It is **not** LUMI's approval database.

For approval interrupts, the interrupt payload carries an existing LUMI `approval_id`.

`PolicyResumeAuthorizer` reads the durable approval decision and verifies:

- organization;
- project;
- AgentRun;
- approval identity;
- final durable status;
- resume decision matches durable approval decision.

Only then does it construct a normalized resume value.

### Important distinction

A human may **reject** a business action.

That rejection is still a valid resume command so the graph can follow its rejection branch.

Therefore:

```text
business decision = rejected
resume command authorization = allowed
```

are not contradictory.

---

## 11. Input interrupts

Input interrupts use:

```text
kind=input
request_key
prompt
schema
```

The default runtime input validator fails closed.

A production input validator must be installed before arbitrary user values may resume a graph.

This prevents an interrupt from becoming an unvalidated data tunnel into graph state.

---

## 12. Safe interrupt authoring

Helpers:

```text
approval_interrupt(...)
input_interrupt(...)
```

create LUMI-owned payload shapes before calling LangGraph `interrupt()`.

The helpers do not make the returned value trusted. Resume still passes through `PolicyResumeAuthorizer`.

Do not put these values in interrupt payloads:

- provider API keys;
- OAuth bearer tokens;
- database DSNs;
- raw customer secrets;
- binary files;
- unrestricted tool arguments not intended for human review.

Use opaque Asset/Artifact/Tool references instead.

---

## 13. Critical LangGraph interrupt restart rule

A LangGraph node containing `interrupt()` is resumed by re-entering that node from its beginning.

This has a direct LUMI engineering consequence:

> Code before `interrupt()` in the same node may execute again after resume.

Therefore the following is unsafe:

```text
charge provider
write external system
interrupt for approval
```

unless the side effect is independently idempotent and reconciliation-safe.

Preferred structure:

```text
prepare decision
interrupt for approval
if approved:
    execute side effect through NODE-20 / NODE-25
```

If side effects must occur in a re-entered node, they must use NODE-20 idempotency/SideEffect Gateway and stable operation keys.

NODE-28 integration verifies:

```text
draft node before checkpoint -> executes once
review node containing interrupt -> enters twice (initial + resume)
finish node -> executes once
```

---

## 14. Checkpoint compare-and-swap

Operation idempotency prevents one control command from being intentionally executed twice.

Checkpoint CAS handles another race:

```text
resume A reads checkpoint cp-1
resume B advances run to cp-2
resume A tries to persist its stale result
```

`PostgresGraphRunStore.persist_snapshot()` requires the expected:

```text
thread_id
checkpoint_namespace
checkpoint_id
```

to match current control metadata before persisting a resumed state.

Mismatch raises:

```text
GRAPH_CHECKPOINT_CONFLICT
```

P0 also takes a PostgreSQL advisory transaction lock:

```text
langgraph-run:<agent_run_id>
```

for control metadata mutations.

---

## 15. Why thread→graph binding is durable

Resume must never determine a graph by:

- asking the client for a new graph version;
- scanning all registered compiled graphs;
- guessing from arbitrary checkpoint state;
- resolving “latest”.

`PostgresGraphRunStore.resolve_thread()` returns the immutable persisted binding:

```text
thread_id
graph_key
graph_version
agent_config_version
task_id
```

`DurableLangGraphExecutor` resolves exactly that compiled graph.

---

## 16. Control-plane operation idempotency

NODE-28 defines `ControlPlaneOperationGuard` as a narrow port.

Production composition must bind this to NODE-20's durable idempotency/side-effect operation machinery.

Control operation types are stable:

```text
langgraph.start
langgraph.resume
langgraph.cancel
```

The operation request hash includes immutable run identity plus input/interrupt/checkpoint semantics.

A replay with the same operation id but a different request hash is a conflict.

P0 unit acceptance uses `MemoryOperationGuard` only as a deterministic double; it is not the production correctness implementation.

---

## 17. Events

`GraphEventSink` receives normalized operational events such as:

```text
agent_run.started
agent_run.interrupted
agent_run.resumed
agent_run.succeeded
agent_run.cancelled
```

Payload is operational metadata only:

- status;
- interrupt count;
- next node names;
- checkpoint id;
- trace id.

The intended production composition is NODE-19 Outbox/Event Runtime.

The control plane does not copy raw prompts, model outputs, credentials or full graph state into event payloads.

---

## 18. State safety

Control-plane contracts reject:

- binary values;
- non-string object keys;
- non-finite numbers;
- excessive nesting.

A graph state may contain application content, but secrets should still be kept behind references whenever possible.

Large binary media must remain Assets/Artifacts, not checkpoint inline payloads.

---

## 19. Subgraphs

Subgraphs are allowed, but they do not create a new authorization plane.

Rules:

1. subgraph nodes inherit the parent AgentRun tenant/project context;
2. subgraph tools still go through NODE-25;
3. paid model calls still go through NODE-22/NODE-27;
4. side effects still use NODE-20;
5. any human pause still maps to LUMI resume authorization;
6. versioned parent graph definition must identify the subgraph versions it expects.

A subgraph must not dynamically load an arbitrary graph version from untrusted state.

---

## 20. Cost and budget integration

NODE-28 does not implement a second budget ledger.

AgentRun/Task/operation model calls continue to use NODE-22 `LedgerBudgetGuard` backed by NODE-27.

Tool-side spend likewise belongs to the shared accounting/side-effect boundaries.

The graph may choose a cheaper eligible path only when product policy allows it; it must not silently weaken explicit hard quality requirements.

A cancelled/failed graph does not imply already incurred provider costs should be reversed.

---

## 21. Cancellation

NODE-28 cancellation terminalizes LUMI run control and prevents future graph resume.

It does not rewrite immutable LangGraph checkpoint history.

It also cannot magically cancel an already accepted provider/tool operation.

Active work must use its native cooperative cancellation path:

- NODE-22 Model Gateway cancellation;
- NODE-25 Tool Gateway cancellation/side-effect semantics;
- NODE-21 Sandbox cancellation;
- Worker/task cancellation checkpoints.

Financial truth remains governed by NODE-27.

---

## 22. API/client boundary

NODE-28 adds transport-neutral:

```text
GraphControlPlaneAPI
GraphControlPlaneClient
```

Exposed operations:

```text
start
resume
snapshot
cancel
```

The client intentionally has no public attributes for:

- graph registry;
- compiled graph;
- executor;
- checkpointer;
- database connection;
- provider/tool credentials.

A later API routing node can expose authenticated HTTP endpoints over this client without giving callers direct LangGraph objects.

---

## 23. PostgreSQL control-plane privileges

Migration:

```text
0012_langgraph_control_plane
```

Because earlier database setup gives broad default DML privileges to future tables, NODE-28 explicitly narrows them.

Runtime:

```text
agent_graph_definitions: SELECT only
agent_run_control: SELECT + INSERT + UPDATE
```

Runtime cannot DELETE control history and cannot mutate graph definition policy.

---

## 24. Restart acceptance

NODE-28 includes two distinct real integrations.

### Current LangGraph in-memory contract

```text
StateGraph
+ InMemorySaver
+ interrupt()
+ Command(resume=...)
```

This validates current execution API semantics.

### PostgreSQL durable restart

Acceptance sequence:

```text
create isolated checkpoint schema
setup official AsyncPostgresSaver
compile graph
start -> interrupt
close saver / discard compiled graph/control plane
reopen saver without setup
recompile exact graph version
load persistent thread binding
resume same interrupt
succeed
```

This verifies resume does not depend on in-memory executor identity.

---

## 25. Graph definition deployment

Recommended deployment flow:

```text
build exact graph definition
calculate content_hash
install/verify durable graph catalog with admin credentials
initialize checkpoint schema with admin credentials if needed
compile graph with runtime checkpointer
register exact compiled graph version
accept traffic
```

Never mutate a live version's graph semantics in place.

---

## 26. Error model

Normalized failures include:

```text
GRAPH_NOT_FOUND
GRAPH_DISABLED
GRAPH_VERSION_CONFLICT
GRAPH_RUN_CONFLICT
GRAPH_RUN_NOT_FOUND
GRAPH_RUN_TERMINAL
GRAPH_INTERRUPT_NOT_FOUND
GRAPH_RESUME_DENIED
GRAPH_CHECKPOINT_REQUIRED
GRAPH_CHECKPOINT_CONFLICT
GRAPH_EXECUTION_FAILED
GRAPH_CANCELLATION_FAILED
```

Raw LangGraph/checkpointer exceptions are wrapped at the adapter boundary rather than returned to product UI as implementation details.

---

## 27. Observability

Each run can be correlated by:

```text
organization_id
project_id
agent_run_id
thread_id
graph_key
graph_version
checkpoint_id
trace_id
```

Later LangSmith/observability nodes may attach traces to the same identities.

Trace systems are observational; they are not checkpoint or financial truth.

---

## 28. Security boundary

`apps/agent-runtime/.../control_plane` is statically scanned for ambient authority.

Forbidden direct imports/markers include examples such as:

- provider SDKs;
- Docker SDK/socket;
- `subprocess`;
- broad HTTP client use;
- provider/cloud API-key environment markers.

The Postgres control store is DB-SDK-neutral and receives a trusted connection factory.

---

## 29. Deterministic tests

Unit coverage includes:

- duplicate start -> one graph execution;
- graph version/config binding;
- client resume value is ignored in favor of authorized normalized value;
- wrong interrupt id never reaches executor;
- denied resume never reaches executor;
- terminal run cannot resume;
- checkpoint CAS rejects stale persistence;
- non-finite graph state rejected;
- durable business rejection resumes with normalized rejected value;
- pending approval blocks resume;
- tenant-mismatched approval blocks resume;
- client does not expose registry/executor/checkpointer.

---

## 30. CI gates

Dedicated workflow:

```text
.github/workflows/langgraph-control-plane.yml
```

Sequential gates:

### graph-contract

- compile control-plane code;
- static architecture contract;
- deterministic unit tests.

### graph-quality

- frozen workspace install;
- Ruff;
- Pyright;
- current LangGraph in-memory interrupt/checkpoint integration.

### graph-postgres

- database migration/seed;
- PostgreSQL control metadata/CAS/privilege acceptance;
- official PostgreSQL LangGraph saver restart acceptance;
- migration downgrade/upgrade smoke.

Hosted PASS is not claimed until GitHub provides a real runner and all required gates execute green.

---

## 31. P0 limitations

Deliberately deferred:

1. full authenticated HTTP routes for control-plane commands;
2. a distributed cancellation bus for already-running node tasks;
3. dynamic graph deployment UI;
4. graph rollout percentages/canaries;
5. state-schema migration between graph versions;
6. production admin UI for graph catalog enable/disable;
7. LangSmith trace policy and trace retention;
8. time-travel/fork UI;
9. arbitrary remote graph loading;
10. automatic resume of human input without LUMI policy.

---

## 32. Definition of Done boundary

NODE-28 implementation scope is:

```text
immutable graph registry
+ AgentRun/thread control binding
+ durable checkpointer requirement
+ current LangGraph adapter
+ PostgreSQL saver factory
+ restart-safe resume
+ NODE-20 operation guard port
+ Approval/Input resume policy
+ checkpoint CAS
+ lifecycle events
+ client/API boundary
+ deterministic unit/integration tests
+ PostgreSQL acceptance
+ docs
+ CI
```

The node must remain:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

until hosted required gates execute green.

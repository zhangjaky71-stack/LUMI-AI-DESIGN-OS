# NODE-28 Acceptance — LangGraph Control Plane

> Branch: `node-28-langgraph-control-plane`  
> Base: `node-27-cost-ledger`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Hosted success is not claimed until required jobs receive a runner and execute green.

---

## 1. Core boundary

NODE-28 implements the LUMI control layer around LangGraph durable execution.

Accepted architecture:

```text
caller
→ GraphControlPlaneClient
→ LangGraphControlPlane
→ exact immutable graph version
→ DurableLangGraphExecutor
→ LangGraph checkpointer
```

LUMI remains authoritative for:

- tenant/project/AgentRun scope;
- graph/config version binding;
- Approval/input policy;
- NODE-20 operation idempotency;
- NODE-25 tool permissions/HITL;
- NODE-22 model execution;
- NODE-27 provider-cost budget/accounting.

---

## 2. Immutable graph definition

Implemented fields:

- [x] graph_key
- [x] graph_version
- [x] agent_config_version
- [x] state_schema_version
- [x] input_schema_version
- [x] output_schema_version
- [x] interrupt_policy_version
- [x] content hash
- [x] enabled flag

Same graph key/version with different content is rejected.

Runtime does not resolve “latest” while resuming an existing AgentRun.

---

## 3. Durable graph catalog

Migration:

```text
0012_langgraph_control_plane
```

Adds:

```text
agent_graph_definitions
agent_run_control
```

Graph definition policy is runtime SELECT-only.

Control metadata is runtime SELECT/INSERT/UPDATE, but runtime DELETE is denied.

---

## 4. AgentRun/thread binding

Each control record freezes:

```text
organization
project
AgentRun
task?
graph key/version
agent config version
graph definition hash
thread_id
```

A replay with different binding semantics fails closed.

Thread is unique within an organization.

---

## 5. Checkpoint correctness

Production compiled graph registration requires a non-null checkpointer.

Control metadata stores:

- checkpoint id;
- checkpoint namespace;
- normalized active interrupts;
- next nodes;
- control status.

A stale resumed result cannot overwrite a newer checkpoint pointer.

Acceptance includes explicit checkpoint CAS failure.

---

## 6. Start idempotency

Unit acceptance:

```text
same start operation twice
→ operation guard invocation count = 1
→ graph start count = 1
→ same checkpoint result replayed
```

Production composition must map `ControlPlaneOperationGuard` to NODE-20 durable idempotency machinery.

---

## 7. Resume security

Required order:

```text
load current run
→ require interrupted
→ require exact interrupt id
→ operation guard
→ re-read fresh run
→ durable Approval/Input authorization
→ verify interrupt binding
→ Command(resume=normalized value)
→ checkpoint CAS
```

The raw client `request.value` is never directly sent to LangGraph by the control plane.

Unit acceptance injects a forged client value and verifies the executor receives only the LUMI-authorized normalized value.

---

## 8. Durable Approval semantics

`PolicyResumeAuthorizer` validates:

- organization;
- project;
- AgentRun;
- approval id;
- final approval status;
- requested resume decision agrees with durable decision.

Covered cases:

- [x] approved approval may resume;
- [x] rejected approval may legitimately resume a rejection branch;
- [x] pending approval does not authorize resume;
- [x] tenant-mismatched approval fails;
- [x] forged client payload does not become normalized approval payload.

---

## 9. Input interrupts

Default input resume policy fails closed.

An explicit `ResumeInputValidator` is required before arbitrary user input can resume a graph.

---

## 10. Current LangGraph integration

Script:

```text
scripts/integration_langgraph_control_plane.py
```

Uses current LangGraph primitives:

```text
StateGraph
InMemorySaver
interrupt()
Command(resume=...)
```

Acceptance sequence:

```text
start
→ draft node
→ review interrupt
→ checkpoint
→ resume through control plane
→ finish
```

Expected execution counters:

```text
draft  = 1
review = 2
finish = 1
```

This proves the pre-interrupt completed node is not re-run, while the node containing `interrupt()` re-enters from its beginning on resume.

---

## 11. Side-effect rule

Because interrupted nodes re-enter, NODE-28 requires:

- side effects after approval when possible;
- otherwise stable NODE-20 idempotency keys;
- external writes through NODE-25 Tool Gateway;
- paid model invocation through NODE-22/NODE-27;
- no assumption that Python code before `interrupt()` executes exactly once.

---

## 12. PostgreSQL restart acceptance

Script:

```text
scripts/integration_langgraph_postgres_checkpoint.py
```

Authored sequence:

1. create isolated checkpoint schema;
2. setup official AsyncPostgresSaver with admin authority;
3. compile exact graph version;
4. start until interrupt;
5. close saver and discard old executor/control plane;
6. reopen saver without setup;
7. reconstruct exact graph version;
8. resolve thread binding from Postgres control store;
9. resume same interrupt;
10. succeed from persisted checkpoint.

This is the durability acceptance for process/runtime reconstruction.

---

## 13. PostgreSQL control metadata acceptance

Script:

```text
scripts/integration_langgraph_postgres_control.py
```

Covers:

- start binding is created once;
- replay sees the same control record;
- thread resolves exact graph/config binding;
- stale checkpoint persist is rejected;
- correct checkpoint CAS succeeds;
- graph definition is visible to runtime;
- runtime cannot update/delete graph definitions;
- runtime cannot delete AgentRun control state.

---

## 14. Durable graph catalog installer

`PostgresGraphDefinitionCatalog` supports admin installation/verification.

Same graph version + different content/config/schema semantics raises a version conflict.

Runtime verification fails if deployed code differs from durable catalog or catalog entry is disabled.

---

## 15. Cancellation boundary

NODE-28 cancellation terminalizes LUMI run control and prevents future graph resume.

It does not rewrite checkpoint history and does not pretend to undo already accepted provider/tool work.

In-flight cancellation remains delegated to Model/Tool/Sandbox/Worker cooperative cancellation boundaries.

---

## 16. Client boundary

`GraphControlPlaneClient` exposes only:

```text
start
resume
snapshot
cancel
```

Client boundary test verifies it does not expose:

- registry;
- executor;
- checkpointer;
- compiled graph registry;
- graph store.

---

## 17. Static architecture contract

Primary validator used by CI:

```text
scripts/validate_langgraph_control_plane_contract_v2.py
```

It checks:

- 0012 migration and privilege narrowing;
- immutable graph/version contracts;
- operation guard on start/resume/cancel;
- fresh re-read before resume;
- authorized normalized resume value;
- exact interrupt binding;
- durable thread→graph resolver;
- checkpointer required;
- official Postgres saver factory;
- Postgres run lock/CAS;
- graph catalog immutability;
- Approval/input policy;
- current LangGraph integration;
- PostgreSQL restart acceptance;
- no ambient provider/Docker/subprocess authority in control-plane package;
- exploratory thread-scanning adapter not exported as production API.

---

## 18. Tests authored

### Unit

```text
apps/agent-runtime/tests/test_control_plane.py
apps/agent-runtime/tests/test_resume_policy.py
apps/agent-runtime/tests/test_control_plane_client.py
```

### Current LangGraph execution

```text
scripts/integration_langgraph_control_plane.py
```

### PostgreSQL control metadata

```text
scripts/integration_langgraph_postgres_control.py
```

### PostgreSQL LangGraph checkpoint restart

```text
scripts/integration_langgraph_postgres_checkpoint.py
```

---

## 19. CI

Dedicated workflow:

```text
.github/workflows/langgraph-control-plane.yml
```

Required sequential gates:

1. `graph-contract`
2. `graph-quality`
3. `graph-postgres`

No hosted PASS is claimed until these jobs actually execute on a runner.

---

## 20. Status discipline

The repository has had a persistent GitHub Actions account payment/spending-limit issue on preceding nodes.

NODE-28 must inspect its own workflow after the Draft PR is opened.

If the first required job again has:

```text
steps=[]
runner_id=0
billing/spending-limit annotation
```

status is:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

If a runner starts and code fails, it is an engineering defect and must be fixed rather than classified external.

---

## 21. Deferred scope

Not claimed:

- full authenticated HTTP control routes;
- distributed in-flight cancellation bus;
- graph rollout/canary UI;
- state schema migration between graph versions;
- LangSmith lifecycle/retention policy;
- time-travel/fork product UI;
- arbitrary remote graph loading;
- automatic unvalidated input resume.

---

## 22. Definition of Done status

Implementation scope authored:

```text
immutable graph registry
+ durable graph catalog
+ AgentRun/thread control store
+ checkpoint CAS
+ current LangGraph executor
+ Postgres checkpointer factory
+ restart-safe resume
+ Approval/input policy
+ NODE-20 operation guard port
+ lifecycle events
+ API/client boundary
+ unit/current-LangGraph/PostgreSQL tests
+ docs
+ CI
```

**COMPLETE remains false until hosted gates execute green.**

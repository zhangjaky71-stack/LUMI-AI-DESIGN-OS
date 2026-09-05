# NODE-09 Acceptance Report

> Status: **IMPLEMENTED / VALIDATING**  
> Node: **NODE-09 — Domain Model**  
> Branch: `node-09-domain-model`  
> Stacked PR: `#7` → base `node-08-canvas-technology-spike`  
> External CI condition: GitHub hosted runners currently fail provisioning with `runner_id=0 / steps=[]` before tests execute.

---

## 1. Acceptance intent

NODE-09 freezes LUMI business semantics before database, HTTP API, event transport and agent runtime implementation. The domain layer must remain independent from:

```text
SQLAlchemy / database schema
FastAPI / HTTP transport
LangGraph checkpoint/runtime state
LangChain / Deep Agents implementation
PixiJS / renderer state
provider SDK response/exception types
object storage SDKs
```

## 2. Implemented outputs

### Shared Python domain package

```text
services/domain/src/lumi_domain/
├── contexts.py
├── entities.py
├── errors.py
├── events.py
├── ids.py
├── invariants.py
├── ports.py
├── states.py
└── value_objects.py
```

The package is exposed to Ruff/Pyright/Pytest through root tooling config without adding runtime framework/provider dependencies.

### Documentation

- `docs/domain/DOMAIN-MODEL.md`
- bounded-context map
- semantic entity relationship diagram
- state-machine diagrams
- ownership map for NODE-10+ responsibilities

### Tests

`services/domain/tests/test_domain_model.py` expresses the domain contract as executable tests rather than prose-only rules.

## 3. Bounded contexts

Machine-readable `BoundedContext` contains exactly 12 contexts:

1. Identity & Tenancy
2. Workspace / Project
3. Brand
4. Asset
5. Design
6. Artifact & Version
7. Agent Execution
8. Workflow / Task
9. Generation / Provider
10. Billing / Cost
11. Collaboration
12. Audit / Governance

## 4. Core aggregates/entities

Implemented semantic skeletons:

```text
Organization
Workspace
Project
Brand
Asset
DesignDocument
Artifact
ArtifactVersion
ArtifactBranch
AgentRun
Task
Generation
CostEntry
```

Tenant-scoped entities expose `organization_id`. `Organization` is the tenant ownership root itself.

## 5. Domain ID contract

`new_uuid7()` implements RFC 9562 UUIDv7 layout using Python standard library primitives only.

Properties under test:

- UUID version is 7;
- timestamp is recoverable;
- later millisecond timestamps sort after earlier IDs;
- no database-generated auto-increment identity dependency;
- provider-native IDs remain separate `ProviderRef` values.

## 6. Value-object contract

Implemented:

```text
Money
Dimensions
Point
Rect
Transform
Color
MimeType
StorageRef
ProviderRef
ModelRef
VersionRef
Usage
Budget
RightsPolicy
OperationIdentity
NormalizedProviderError
```

Important rules:

- `Money.amount` accepts `Decimal`, never float;
- `StorageRef` requires bucket/key/SHA-256 checksum/owner organization;
- `OperationIdentity` requires domain operation ID + non-empty idempotency key;
- provider errors are normalized without importing any provider SDK.

## 7. State-machine contract

### Project

```text
DRAFT → ACTIVE → PAUSED → ACTIVE
DRAFT/ACTIVE/PAUSED → ARCHIVED
ARCHIVED is terminal
```

### AgentRun

```text
PENDING → RUNNING
RUNNING ↔ WAITING_USER
RUNNING ↔ PAUSED
RUNNING/WAITING_USER/PAUSED → CANCEL_REQUESTED → CANCELLED
RUNNING → SUCCEEDED | FAILED
terminal states cannot resume
```

### Task

```text
PENDING → READY → RUNNING → SUCCEEDED
RUNNING → WAITING_USER → RUNNING
RUNNING → WAITING_DEPENDENCY → READY
RUNNING → FAILED → READY
pending/ready/running/waiting states may be cancelled where declared
```

### ArtifactVersion

```text
DRAFT → READY → APPROVED
DRAFT/READY → REJECTED
APPROVED and REJECTED are terminal
```

Approved versions cannot be revised in place.

## 8. Ten domain invariants

| # | Invariant | Code/Test expression |
|---:|---|---|
| 1 | Tenant business objects carry `organization_id` | dataclass field structural test |
| 2 | Access requires tenant membership | `require_tenant_membership` |
| 3 | Artifact lineage cannot cycle | `assert_artifact_lineage_acyclic` |
| 4 | Task dependency graph cannot cycle | `assert_task_graph_acyclic` |
| 5 | Cost ledger entries are append-only | frozen `CostEntry` + reversal/adjustment |
| 6 | Approved ArtifactVersion cannot be overwritten | terminal state + `revised()` guard |
| 7 | Hard constraint violation requires override audit | `require_hard_constraint_override` |
| 8 | Paid side effect requires operation/idempotency identity | `Generation` + invariant helper |
| 9 | Storage object requires checksum + tenant ownership | `StorageRef` + `Asset.__post_init__` |
| 10 | Provider error cannot leak directly into domain state | `normalize_provider_error` + static import boundary |

`CostEntry.metadata` is copied into `MappingProxyType`, preventing mutation through either the original input dictionary or the entity's exposed mapping.

## 9. Critical semantic separations

### Asset vs Artifact

```text
Asset    = input/reference/imported resource
Artifact = produced/versioned deliverable/result
```

### DesignDocument vs ArtifactVersion

```text
DesignDocument = editable structured design identity
ArtifactVersion = immutable deliverable/version lineage node
```

### Project State vs LangGraph State

```text
Project state   = business truth
LangGraph state = execution/checkpoint context
```

LangGraph does not own the Project lifecycle.

### Domain object vs renderer object

Design/Artifact semantics do not import or persist Pixi scene objects. NODE-08 renderer state remains disposable.

## 10. Repository and service ports

Repository Protocols:

```text
ProjectRepository
AssetRepository
ArtifactRepository
TaskRepository
AgentRunRepository
CostLedgerRepository
```

Service Protocols:

```text
ProjectService
BrandPolicyService
DesignOperationService
ArtifactVersionService
TaskGraphService
GenerationService
CostLedgerService
ApprovalService
AccessPolicyService
```

NODE-10+ implement adapters outside `lumi_domain`.

## 11. Domain event vocabulary

Frozen semantic event names:

```text
project.created
asset.ready
agent_run.started
agent_run.waiting_user
artifact.version_created
artifact.approved
task.succeeded
generation.completed
cost.recorded
```

NODE-12 owns envelope/versioning/delivery semantics.

## 12. Static boundary contract

A test scans `lumi_domain` source and rejects imports from:

```text
sqlalchemy
fastapi
httpx
langchain
langgraph
openai
anthropic
google.genai
boto3
```

This is intentionally simple and explicit: the core domain must not silently acquire framework/provider coupling.

## 13. Validation status

Implemented test coverage includes:

```text
UUIDv7 ordering/timestamp
12 bounded contexts
organization_id structural coverage
Decimal-only Money
Project transitions
AgentRun wait/resume/cancel transitions
Task wait/dependency/retry transitions
ArtifactVersion approval immutability
Artifact lineage cycle rejection
Task DAG cycle rejection
Storage checksum/ownership
Tenant membership
Hard constraint override audit
Paid side-effect idempotency identity
Deep CostEntry immutability + reversal/adjustment
Provider error normalization
Forbidden dependency imports
```

### Current external blocker

The stacked PR was opened while GitHub hosted runner provisioning is unhealthy. PR-triggered workflows can fail before checkout/setup with:

```text
runner_id: 0
runner_name: ""
steps: []
```

Those executions provide no Ruff/Pyright/Pytest evidence and are not counted as test failures or passes.

## 14. Completion gate

NODE-09 remains `IMPLEMENTED / VALIDATING` until a real runner executes and passes:

```text
Ruff format
Ruff lint
Pyright
Pytest including services/domain/tests
contracts
existing regression gates
secret scan
dependency review
```

After green validation:

1. mark NODE-09 `COMPLETE`;
2. update `docs/NODE-INDEX.md` to NODE-10;
3. merge/retarget in dependency order after PR #6 is mergeable and merged;
4. start `NODE-10 — Database Schema`.

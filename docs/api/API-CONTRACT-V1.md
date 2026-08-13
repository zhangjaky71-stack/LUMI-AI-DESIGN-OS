# LUMI AI Design OS — API Contract V1

> Node: `NODE-11`  
> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Contract prefix: `/api/v1`  
> OpenAPI: 3.1  
> Transport implementation: FastAPI + Pydantic v2  
> Business implementation: application-service adapters from later Nodes

---

## 1. Contract rule

The API is a transport contract over the NODE-09 domain model. It is not the domain model, ORM model, LangGraph state or provider schema.

```text
HTTP request
  ↓
Pydantic transport DTO
  ↓
ApiV1Gateway application-service port
  ↓
Domain/service layer
  ↓
Persistence / Agent / Provider adapters
```

Forbidden endpoint behavior:

```text
route handler -> SQLAlchemy Session
route handler -> provider SDK
route handler -> LangGraph graph mutation
route handler -> renderer object
```

The transport package contains a static boundary test rejecting those imports.

## 2. Versioning

All product resource routes are under:

```text
/api/v1/...
```

Versioning policy:

- additive compatible fields may be added inside V1;
- existing field meaning may not silently change;
- removing/renaming required fields requires a new major API version or a documented compatibility window;
- stable `operationId` values are part of the SDK contract;
- provider-native APIs never leak directly into the public LUMI API.

OpenAPI document endpoint for the contract server:

```text
/api/openapi.json
```

Developer docs:

```text
/api/docs
/api/redoc
```

## 3. Request identity

Every response carries:

```text
X-Request-Id
```

Clients may submit an `X-Request-Id` up to 128 characters. Otherwise LUMI generates a UUIDv7 request ID.

The same request ID is included in Problem Details responses.

Future tracing Nodes may map request ID to LangSmith/OTel trace IDs, but the HTTP request identifier remains provider-agnostic.

## 4. Tenant selector

Business routes require:

```text
X-Lumi-Organization-Id: <uuid>
```

This is a **tenant selector, not authorization**.

NODE-16 must validate that the authenticated principal has membership/permission for the selected organization. Possession of an organization UUID never grants access.

The tenant selector is passed to the application gateway as immutable `RequestContext.organization_id`.

## 5. Response envelopes

Single resource:

```json
{
  "data": {},
  "meta": {
    "request_id": "..."
  }
}
```

Collection:

```json
{
  "data": [],
  "meta": {
    "request_id": "...",
    "next_cursor": "opaque-or-null",
    "has_more": false
  }
}
```

API clients must not infer total counts unless a resource explicitly publishes them.

## 6. Cursor pagination

Collection query contract:

```text
cursor? : opaque string
limit   : 1..100, default 50
```

Rules:

- cursor is opaque to clients;
- cursor semantics belong to the application/repository adapter;
- never expose raw SQL offsets or internal DB primary-key assumptions as a public promise;
- ordering must be deterministic for any cursor implementation.

## 7. Error contract

Errors use:

```text
Content-Type: application/problem+json
```

Shape:

```json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/v1/projects",
  "code": "REQUEST_VALIDATION_FAILED",
  "request_id": "...",
  "errors": [
    {
      "field": "body.name",
      "code": "string_too_short",
      "message": "String should have at least 1 character"
    }
  ]
}
```

`code` is the stable machine-facing LUMI error identifier. `title/detail/message` are presentation/debug text and must not be parsed for business logic.

Provider error codes are normalized before reaching this layer.

## 8. Idempotency

Durable side-effect requests use:

```text
Idempotency-Key
```

Current V1 side-effect operations include:

```text
createProject
createAsset
createArtifactVersion
createAgentRun
cancelAgentRun
resumeAgentRun
createGeneration
decideApproval
```

The key is scoped by organization in NODE-10 persistence:

```text
UNIQUE (organization_id, idempotency_key)
```

NODE-20 owns exact retry/reconciliation semantics. NODE-11 freezes the transport key and passes it unchanged to the application gateway.

## 9. Optimistic concurrency

Mutable resource operations use entity versions.

Read responses may return:

```text
ETag: W/"<version>"
```

Updates/decisions require the expected version through:

```text
If-Match: W/"<version>"
```

Invalid version syntax returns a stable LUMI problem code.

The DB adapter later uses the version in a tenant-scoped optimistic update:

```text
WHERE id = :id
  AND organization_id = :organization_id
  AND version = :expected_version
```

## 10. Async operation semantics

Operations that start or control long-running work return `202 Accepted` when the application adapter accepts the operation but completion happens later.

Examples:

```text
createAgentRun
cancelAgentRun
resumeAgentRun
createGeneration
```

A `202` response means accepted, not completed.

Clients follow the returned resource ID using GET/streaming APIs added by later execution/realtime Nodes.

## 11. Stable operation inventory

### System

| Method | Path | operationId |
|---|---|---|
| GET | `/api/v1/health` | `getApiV1Health` |

### Projects

| Method | Path | operationId |
|---|---|---|
| GET | `/api/v1/projects` | `listProjects` |
| POST | `/api/v1/projects` | `createProject` |
| GET | `/api/v1/projects/{project_id}` | `getProject` |
| PATCH | `/api/v1/projects/{project_id}` | `updateProject` |
| DELETE | `/api/v1/projects/{project_id}` | `archiveProject` |

### Assets

| Method | Path | operationId |
|---|---|---|
| GET | `/api/v1/assets` | `listAssets` |
| POST | `/api/v1/assets` | `createAsset` |
| GET | `/api/v1/assets/{asset_id}` | `getAsset` |

Asset binary upload/presign/finalization workflow is owned by NODE-26. V1 currently freezes the semantic Asset resource contract only.

### Artifacts

| Method | Path | operationId |
|---|---|---|
| GET | `/api/v1/artifacts/{artifact_id}` | `getArtifact` |
| GET | `/api/v1/artifacts/{artifact_id}/versions` | `listArtifactVersions` |
| POST | `/api/v1/artifacts/{artifact_id}/versions` | `createArtifactVersion` |

Artifact export/download transport is added with the Artifact/Export Nodes rather than guessing file-delivery semantics now.

### Agent Runs

| Method | Path | operationId |
|---|---|---|
| POST | `/api/v1/agent-runs` | `createAgentRun` |
| GET | `/api/v1/agent-runs/{agent_run_id}` | `getAgentRun` |
| POST | `/api/v1/agent-runs/{agent_run_id}:cancel` | `cancelAgentRun` |
| POST | `/api/v1/agent-runs/{agent_run_id}:resume` | `resumeAgentRun` |

### Tasks

| Method | Path | operationId |
|---|---|---|
| GET | `/api/v1/tasks/{task_id}` | `getTask` |

Task mutation/scheduler-internal APIs remain private to workflow Nodes until a product-facing need is defined.

### Generations

| Method | Path | operationId |
|---|---|---|
| POST | `/api/v1/generations` | `createGeneration` |
| GET | `/api/v1/generations/{generation_id}` | `getGeneration` |

`provider` and `model` may be omitted by callers so the Model Gateway can route according to the NODE-07 policy. Public callers do not need to hardcode a vendor.

### Approvals

| Method | Path | operationId |
|---|---|---|
| POST | `/api/v1/approvals/{approval_id}:decide` | `decideApproval` |

Approval decision is idempotent and version-checked.

## 12. Transport DTO policy

DTOs use `extra="forbid"`.

Purpose:

- reject typo fields instead of silently discarding them;
- keep public contract changes explicit;
- prevent provider/ORM blobs from leaking into API responses unnoticed.

DTO families currently frozen:

```text
ProjectCreate / ProjectPatch / ProjectResource
AssetCreate / AssetResource
ArtifactResource
ArtifactVersionCreate / ArtifactVersionResource
AgentRunCreate / AgentRunResumeRequest / AgentRunResource
TaskResource
GenerationCreate / GenerationResource
ApprovalDecisionRequest / ApprovalResource
HealthResource
ProblemDetails
DataEnvelope / CollectionEnvelope
```

## 13. Application gateway boundary

`ApiV1Gateway` is a Protocol implemented by later application-service Nodes.

The default contract server has no business adapter. Valid business requests therefore fail explicitly with:

```text
501 APPLICATION_SERVICE_NOT_INSTALLED
```

This is intentional during contract-first implementation. It proves the route does not fall through to ad-hoc ORM/provider access.

Later wiring:

```python
install_api_v1(app, gateway=real_application_gateway)
```

must not change operation IDs or DTO meaning.

## 14. Standalone contract server

NODE-11 exposes:

```text
lumi_api.app_v1:app
```

for OpenAPI inspection and transport-contract tests independent of later business services.

## 15. OpenAPI source of truth

The canonical schema is generated from the FastAPI/Pydantic contract:

```bash
python scripts/export_api_v1_contract.py
python scripts/export_api_v1_contract.py --check
```

Target snapshot:

```text
contracts/api/openapi-v1.json
```

The checked snapshot must be generated, never manually patched.

## 16. TypeScript client generation

NODE-11 includes a dependency-free generator:

```bash
python scripts/generate_api_v1_client.py
python scripts/generate_api_v1_client.py --check
```

Target:

```text
packages/api-client-v1/src/generated.ts
```

The generator reads the actual OpenAPI 3.1 document and emits:

- component schema TypeScript types;
- stable `ApiV1OperationMap`;
- method/path runtime operation metadata.

This avoids introducing an additional codegen package/lock dependency while GitHub Actions dependency resolution is externally blocked.

A higher-level browser/client wrapper may build on this generated map without redefining DTOs.

## 17. Contract tests

`apps/api/tests/test_api_v1_contract.py` verifies:

```text
OpenAPI 3.1
all product routes under /api/v1
exact stable operationId set
operationId uniqueness
tenant header behavior
idempotency/concurrency header behavior
cursor limit 1..100
ProblemDetails component
validation errors use application/problem+json
X-Request-Id propagation
default gateway fails explicitly
transport package does not import ORM/agent/provider SDKs
```

## 18. Security boundaries

NODE-11 does not implement authentication/authorization.

It intentionally does **not** claim:

```text
X-Lumi-Organization-Id proves membership
client-provided user ID proves identity
project ID implies access
provider response is safe to expose
```

NODE-16 owns identity, membership, RBAC and tenant authorization.

## 19. Ownership deferred to later Nodes

NODE-11 does not implement:

- Project business services (`NODE-17`);
- Asset upload pipeline (`NODE-26`);
- Agent orchestration (`NODE-28+`);
- provider execution (`Model Gateway nodes`);
- streaming/realtime transport;
- billing reconciliation;
- auth/RBAC;
- collaboration APIs;
- export delivery.

It freezes the contract surface those implementations must respect.

## 20. Current validation boundary

NODE-11 remains **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL** until:

1. GitHub Actions billing/spending is repaired;
2. NODE-10 Python dependency lock is genuinely regenerated/committed;
3. FastAPI contract tests execute on Python 3.12;
4. canonical OpenAPI snapshot is generated and checked in;
5. TypeScript generated client is generated and checked in;
6. contract `--check` commands pass;
7. existing NODE-06/07 contract, eval and security gates remain green.

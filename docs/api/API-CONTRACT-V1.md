# LUMI AI Design OS — Public API Contract V1

> Node: NODE-11  
> Status: IMPLEMENTED / VALIDATING  
> Date: 2026-08-16  
> Base path: `/api/v1`  
> Executable contract: `apps/api/src/lumi_api/api/v1/`

## 1. Contract purpose

The public API is a stable transport contract over LUMI application/domain services. It is **not** a serialization of SQLAlchemy rows and it is **not** a LangGraph state endpoint.

Dependency direction:

```text
HTTP / OpenAPI
      ↓
Pydantic API request/response schemas
      ↓
ApiV1Service application port
      ↓
application/domain services
      ↓
repositories/providers/orchestration adapters
```

The `api.v1` package must not import ORM models, SQLAlchemy sessions, provider SDKs or LangGraph implementation state.

## 2. Versioning

P0 uses URI major-versioning:

```text
/api/v1/...
```

Rules:

1. Backward-compatible field additions may ship within v1.
2. Existing required request fields are not changed incompatibly within v1.
3. Existing enum values are not silently renamed.
4. Removing/renaming fields, changing semantics, or changing resource identity requires a new major contract or an explicit compatibility path.
5. Provider-native errors/statuses never become public domain enum values by accident.

## 3. Tenant scope

Every P0 business endpoint requires:

```http
X-Organization-ID: <UUID>
```

This header selects the tenant scope; it is **not authorization by itself**.

The application adapter must:

1. authenticate the caller;
2. establish the requested organization scope;
3. verify membership/role before business access;
4. open the NODE-10 tenant DB session/RLS context;
5. execute the domain/application operation.

A caller choosing another organization UUID does not grant access.

## 4. Request correlation

Clients may send:

```http
X-Request-ID: client-generated-id
```

The API only accepts a bounded safe character set. If missing/invalid, the server generates a UUIDv7 request ID.

Every response carries:

```http
X-Request-ID: ...
```

Problem Details payloads include the same `request_id`.

## 5. Idempotency

Retry-sensitive mutations require:

```http
Idempotency-Key: <8..255 chars>
```

Current required operations:

```text
POST /projects
POST /projects/{project_id}/tasks
POST /projects/{project_id}/agent-runs
POST /agent-runs/{agent_run_id}/cancel
POST /projects/{project_id}/generations
```

The key is tenant scoped. NODE-10 persistence enforces uniqueness of `(organization_id, idempotency_key)` for paid/external side effects.

Semantics:

- same key + equivalent request → return/replay the original operation result where supported;
- same key + conflicting request hash → `409 idempotency_conflict`;
- a retry must not create a second paid generation merely because the first HTTP response was lost.

## 6. Optimistic concurrency

Mutable resources expose a numeric `version` and return:

```http
ETag: W/"7"
```

Project mutations require:

```http
If-Match: W/"7"
```

The service passes `expected_version=7` to the application/persistence layer. NODE-10 writes use `WHERE version = expected_version` and increment version atomically.

Stale writes must become a stable conflict/precondition error rather than a blind overwrite.

P0 currently applies this explicitly to:

```text
PATCH /projects/{project_id}
POST  /projects/{project_id}/transitions
```

Task/AgentRun/Generation responses also expose version/ETag so later safe mutation endpoints can use the same rule.

## 7. Pagination

List endpoints use opaque cursor pagination:

```http
GET /api/v1/projects?cursor=<opaque>&limit=50
GET /api/v1/projects/{project_id}/tasks?cursor=<opaque>&limit=50
```

Constraints:

```text
1 <= limit <= 100
cursor <= 2048 chars
```

Response shape:

```json
{
  "items": [],
  "meta": {
    "next_cursor": null,
    "has_more": false
  }
}
```

Clients must not parse or synthesize cursor internals.

## 8. Error contract

Errors use:

```http
Content-Type: application/problem+json
```

Payload:

```json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more request fields are invalid.",
  "code": "validation_error",
  "request_id": "...",
  "instance": "/api/v1/projects",
  "errors": []
}
```

`code` is the machine-stable discriminator. Human text may evolve.

Reserved v1 application error codes:

```text
validation_error
unauthenticated
forbidden
not_found
version_conflict
idempotency_conflict
invalid_transition
budget_exceeded
rights_restricted
provider_unavailable
rate_limited
request_cancelled
api_service_not_configured
internal_error
```

Application adapters must map domain/provider failures into these public semantics rather than exposing raw SDK exceptions or SQL messages.

## 9. P0 resources

### Project

Public fields:

```text
id
organization_id
workspace_id
name
status
brief
brand_id
active_branch_id
settings
version
created_at
updated_at
```

Status values come directly from NODE-09:

```text
draft
active
paused
archived
```

Create:

```http
POST /api/v1/projects
```

Read/list:

```http
GET /api/v1/projects
GET /api/v1/projects/{project_id}
```

Patch mutable data:

```http
PATCH /api/v1/projects/{project_id}
If-Match: W/"<version>"
```

Lifecycle transition:

```http
POST /api/v1/projects/{project_id}/transitions
If-Match: W/"<version>"

{"target":"active"}
```

Lifecycle changes do not hide inside arbitrary PATCH fields.

### Task

Create/list/read:

```http
GET  /api/v1/projects/{project_id}/tasks
POST /api/v1/projects/{project_id}/tasks
GET  /api/v1/tasks/{task_id}
```

Create input includes:

```text
task_type
name
dependency_ids
priority
max_attempts
input
```

Task status uses the NODE-09 enum:

```text
pending
ready
running
waiting_user
waiting_dependency
succeeded
failed
cancelled
```

The API does not let clients submit a completed status during create.

### AgentRun

Create:

```http
POST /api/v1/projects/{project_id}/agent-runs
Idempotency-Key: ...
```

Request is product-level intent:

```text
goal
budget?
client_context
```

Clients do **not** choose `graph_version` or `agent_config_version`; those are server/runtime decisions returned for traceability.

Read/cancel:

```http
GET  /api/v1/agent-runs/{agent_run_id}
POST /api/v1/agent-runs/{agent_run_id}/cancel
```

Cancel is an idempotent request/acceptance action; it does not promise the provider/runtime has already stopped when HTTP 202 is returned.

### Generation

Create:

```http
POST /api/v1/projects/{project_id}/generations
Idempotency-Key: ...
```

Request:

```text
kind: image | image_edit | vector | document | video
prompt
input_asset_ids
model_hint?
parameters
```

`model_hint` is a hint, not a provider bypass. Model Router / policy may choose another allowed provider/model.

Response keeps normalized Generation status:

```text
pending
running
completed
failed
cancelled
```

Raw provider status/error text is not the public status enum. Normalized error shape:

```text
code
message
retryable
details
```

Read:

```http
GET /api/v1/generations/{generation_id}
```

### ArtifactVersion

Read:

```http
GET /api/v1/artifact-versions/{artifact_version_id}
```

ArtifactVersion is historical/versioned output, not a mutable ORM row. It exposes version number, approval status, hash, metadata and provenance-adjacent creator information.

## 10. HTTP status semantics

```text
200 OK       successful read/update/transition
201 Created  synchronous resource creation accepted and resource exists
202 Accepted asynchronous run/generation/cancel request accepted
400          malformed semantic header/request outside field validation
401          unauthenticated
403          authenticated but forbidden
404          resource not found in authorized tenant scope
409          idempotency/domain conflict
412          optimistic concurrency / precondition conflict
422          request field validation
429          rate limited
503          dependency/provider/application service unavailable
```

For tenant isolation, adapters should avoid leaking whether a foreign-tenant resource exists. A resource outside the authorized tenant scope should normally behave as not found/forbidden according to the centralized access policy, without exposing foreign metadata.

## 11. Response headers

Versioned mutable resource responses carry:

```http
ETag: W/"<version>"
Cache-Control: private, no-cache
```

Create responses also carry `Location` when a canonical resource URI exists.

## 12. Contract/application boundary

`ApiV1Service` is the only dependency route handlers use.

The default dependency intentionally raises:

```text
503 api_service_not_configured
```

until an application adapter is installed.

This is intentional: NODE-11 must not install an in-memory fake or return fabricated product data merely to make OpenAPI routes appear operational.

Tests override this dependency with a fake service only to exercise HTTP contract behavior.

## 13. Security boundaries

P0 rules:

- Pydantic request models use `extra="forbid"` to reject unknown fields.
- tenant is explicit per request.
- idempotency keys are bounded.
- request IDs are bounded/sanitized.
- provider SDK errors never flow directly to the client.
- ORM/session objects never appear in response models.
- provider credentials/storage URLs are not exposed by these schemas.
- mutable lifecycle changes use explicit commands/transitions.
- raw SQL constraint names/messages are mapped before reaching clients.

Authentication token format and RBAC implementation belong to the auth/application integration nodes; this contract freezes the tenant/access semantics they must satisfy.

## 14. OpenAPI executable source

OpenAPI is generated from:

```python
lumi_api.api.v1.app.create_contract_app()
```

Metadata:

```text
title: LUMI AI Design OS API
version: 1.0.0
openapi URL: /api/openapi.json
docs URL: /api/docs
redoc URL: /api/redoc
```

The executable tests assert the exact P0 path set and required contract headers so accidental route drift fails CI.

## 15. Deferred endpoints

NODE-11 intentionally does not prematurely freeze:

- SSE/WebSocket Agent event stream payloads — NODE-12 event envelope first;
- direct-to-object-store upload intent details — Asset/API adapter integration;
- auth token/refresh endpoints — auth provider implementation;
- collaboration presence/comments — collaboration node;
- knowledge/memory ingestion/search endpoints — knowledge/memory nodes;
- Canvas Design IR operation API — Design IR/Operation Schema nodes;
- provider-specific endpoints — forbidden as public product contract.

## 16. Definition of Done

NODE-11 is COMPLETE only when:

```text
P0 request/response schemas frozen
+ stable error contract
+ tenant/idempotency/concurrency headers frozen
+ cursor pagination frozen
+ OpenAPI path/header contract tests green
+ no ORM/provider/LangGraph leakage
+ repository CI/security green
+ stacked NODE-09/NODE-10 dependencies resolved
+ merged and NODE index updated
```

Until then it remains `VALIDATING` or `BLOCKED_EXTERNAL / VALIDATING` according to evidence.

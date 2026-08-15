# NODE-11 — Acceptance Evidence

> Status: **VALIDATING**  
> Branch: `feat/node-11-api-contract`  
> Stacked Base: `feat/node-10-database-schema` / PR #76  
> Node: API Contract  
> Date: 2026-08-16

## Scope implemented

NODE-11 freezes the first public HTTP contract without exposing ORM rows, provider SDK types or LangGraph checkpoint state.

Implemented:

- `/api/v1` versioned contract app/router;
- strict Pydantic request/response schemas;
- domain status enum reuse from NODE-09;
- `X-Organization-ID` tenant scope on every P0 business operation;
- `Idempotency-Key` on retry-sensitive create/cancel/generation operations;
- `ETag` response semantics and `If-Match` optimistic concurrency on Project mutation/transition;
- opaque cursor pagination contract;
- stable `application/problem+json` Problem Details payload;
- request correlation with safe `X-Request-ID` propagation/generation;
- `ApiV1Service` Protocol as the only route/application dependency;
- explicit `503 api_service_not_configured` default rather than fake success data;
- Project P0 endpoints;
- Task P0 endpoints;
- AgentRun create/read/cancel endpoints;
- Generation create/read endpoints;
- ArtifactVersion read endpoint;
- executable OpenAPI/header/Problem Details tests;
- architecture validator forbidding SQLAlchemy/asyncpg/Alembic/LangGraph/provider SDK imports from `api.v1`;
- dedicated frozen-install API contract workflow.

Canonical documentation:

```text
docs/api/API-CONTRACT-V1.md
```

## P0 path contract

```text
GET   /api/v1/projects
POST  /api/v1/projects
GET   /api/v1/projects/{project_id}
PATCH /api/v1/projects/{project_id}
POST  /api/v1/projects/{project_id}/transitions
GET   /api/v1/projects/{project_id}/tasks
POST  /api/v1/projects/{project_id}/tasks
GET   /api/v1/tasks/{task_id}
POST  /api/v1/projects/{project_id}/agent-runs
GET   /api/v1/agent-runs/{agent_run_id}
POST  /api/v1/agent-runs/{agent_run_id}/cancel
POST  /api/v1/projects/{project_id}/generations
GET   /api/v1/generations/{generation_id}
GET   /api/v1/artifact-versions/{artifact_version_id}
```

The executable validator intentionally freezes the path set so accidental transport drift is reviewed as a contract change.

## Contract invariants

### Tenant

Every P0 business operation requires `X-Organization-ID`. This selects tenant scope only; application authentication/membership authorization remains mandatory before business access.

### Idempotency

Required for:

```text
POST /projects
POST /projects/{id}/tasks
POST /projects/{id}/agent-runs
POST /agent-runs/{id}/cancel
POST /projects/{id}/generations
```

This aligns with NODE-10 tenant-scoped idempotency persistence.

### Optimistic concurrency

Project PATCH/transition requires:

```text
If-Match: W/"<positive-version>"
```

Versioned mutable resources return:

```text
ETag: W/"<version>"
Cache-Control: private, no-cache
```

### Errors

Errors are normalized to `application/problem+json` with:

```text
type
title
status
detail
code
request_id
instance?
errors?
```

Raw SQL/provider exception text is not part of the public contract.

## Executable tests

`apps/api/tests/test_api_v1_contract.py` covers:

1. exact P0 OpenAPI path set;
2. tenant header on every P0 route;
3. idempotency header on retry-sensitive operations;
4. If-Match header on Project mutation/transition;
5. reuse of NODE-09 ProjectStatus values in OpenAPI;
6. create Project returns 201 + Location + ETag + Request ID;
7. missing application service returns explicit 503 Problem Details;
8. validation failures use Problem Details;
9. ETag parsing/round-trip;
10. Decimal money contract.

`tools/node11/validate_api_contract.py` additionally scans the API package AST and rejects direct persistence/provider/orchestration implementation imports.

## Application implementation boundary

NODE-11 intentionally does not install a fake production service. The default dependency fails with:

```text
503 api_service_not_configured
```

A later application adapter must implement `ApiV1Service` by coordinating:

```text
auth/access policy
+ NODE-09 domain rules
+ NODE-10 repositories/transactions
+ NODE-12 events
+ provider/model router
```

This keeps public HTTP schemas stable while implementation can evolve behind the port.

## Deferred contract surfaces

Not frozen prematurely in NODE-11:

- SSE/WebSocket event payloads — NODE-12 first;
- direct object-store upload-intent shape;
- authentication token/refresh protocol;
- collaboration/presence;
- Knowledge/Memory APIs;
- Canvas Design IR operation APIs;
- provider-specific public endpoints.

## GitHub Actions evidence

Pending pull request creation and this node's own workflow result.

The repository currently has an account-level GitHub Actions billing/spending-limit block independently recorded by NODE-08, NODE-09 and NODE-10. NODE-11 must record its own run and must not inherit a PASS/FAIL conclusion from another node.

## Acceptance checklist

- [x] versioned `/api/v1` resource contract implemented.
- [x] Pydantic API schemas are separate from ORM models.
- [x] NODE-09 lifecycle enums are reused.
- [x] tenant header semantics frozen.
- [x] idempotency header semantics frozen.
- [x] ETag / If-Match concurrency contract frozen.
- [x] cursor pagination frozen.
- [x] Problem Details error shape frozen.
- [x] route layer depends on `ApiV1Service` Protocol only.
- [x] architecture validator forbids ORM/provider/LangGraph implementation imports.
- [x] executable HTTP/OpenAPI tests committed.
- [ ] repository Python tests pass.
- [ ] dedicated NODE-11 API contract workflow passes.
- [ ] repository CI/security gates pass.
- [ ] stacked NODE-09/NODE-10 dependencies resolve and merge.
- [ ] NODE-11 merged and NODE index updated to COMPLETE.

NODE-11 remains `VALIDATING`, not `COMPLETE`.

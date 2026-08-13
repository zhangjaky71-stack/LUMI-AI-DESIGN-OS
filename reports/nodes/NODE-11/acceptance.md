# NODE-11 Acceptance Report

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Node: **NODE-11 — API Contract**  
> Branch: `node-11-api-contract`  
> Stack base: `node-10-database-schema`  
> Contract: `/api/v1` + OpenAPI 3.1

---

## 1. Acceptance result so far

NODE-11 has implemented the versioned HTTP contract layer independently from ORM, provider SDKs, LangGraph and renderer state.

Implemented:

- Pydantic v2 transport DTOs;
- standard single/collection envelopes;
- Problem Details error shape;
- request ID middleware;
- tenant selector contract;
- cursor pagination contract;
- idempotency-key dependency;
- If-Match/ETag optimistic-concurrency contract;
- stable operation IDs;
- Project/Asset/Artifact/AgentRun/Task/Generation/Approval routes;
- application-service `ApiV1Gateway` Protocol;
- explicit 501 default when the business adapter is not installed;
- standalone contract server `lumi_api.app_v1:app`;
- OpenAPI canonical exporter;
- dependency-free TypeScript OpenAPI generator;
- transport-boundary tests;
- dedicated API Contract workflow;
- full reference documentation.

The Node is not marked COMPLETE because real runner validation and generated snapshots are blocked by the existing upstream dependency/Actions conditions.

## 2. External blockers inherited from NODE-10

### GitHub Actions billing/spending

GitHub has already reported:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased.
Please check the 'Billing & plans' section in your settings.
```

Jobs can terminate with:

```text
runner_id = 0
runner_name = ""
steps = []
```

No contract test executes in those runs.

### Python lock

NODE-10 introduced SQLAlchemy/Alembic/asyncpg/pgvector and workspace-domain dependency changes. The current `uv.lock` is intentionally not hand-edited and must be genuinely regenerated before `uv sync --frozen` can pass.

NODE-11 inherits that frozen-install blocker.

## 3. Contract boundary

Transport code under:

```text
apps/api/src/lumi_api/api/
```

must not import:

```text
SQLAlchemy
asyncpg
Alembic
LangGraph
LangChain
OpenAI SDK
Anthropic SDK
Google GenAI SDK
```

A static contract test scans the transport package for those imports.

The HTTP layer may depend on NODE-09 domain enums/value semantics but not persistence/runtime implementation types.

## 4. API version and operation inventory

All product routes are under `/api/v1`.

Exactly 20 operation IDs are currently frozen:

```text
getApiV1Health
listProjects
createProject
getProject
updateProject
archiveProject
listAssets
createAsset
getAsset
getArtifact
listArtifactVersions
createArtifactVersion
createAgentRun
getAgentRun
cancelAgentRun
resumeAgentRun
getTask
createGeneration
getGeneration
decideApproval
```

Contract tests require the set and uniqueness to remain stable.

## 5. Response contract

Single resource:

```json
{
  "data": {},
  "meta": {"request_id": "..."}
}
```

Collection:

```json
{
  "data": [],
  "meta": {
    "request_id": "...",
    "next_cursor": null,
    "has_more": false
  }
}
```

## 6. Error contract

Errors are represented as `ProblemDetails` and returned with:

```text
application/problem+json
```

Stable machine fields:

```text
status
code
request_id
errors[].field
errors[].code
```

Validation errors are normalized into the same problem shape.

## 7. Request ID contract

`RequestIdMiddleware`:

- accepts client `X-Request-Id` when length is 1..128;
- otherwise generates UUIDv7;
- stores it in request state;
- writes it back to response `X-Request-Id`;
- includes it in Problem Details.

## 8. Tenant selector contract

Business routes receive:

```text
X-Lumi-Organization-Id
```

The API code/documentation explicitly states that this is not authorization.

NODE-16 must replace/augment the selector with authenticated membership/RBAC enforcement without changing resource DTO semantics.

## 9. Pagination contract

List routes use:

```text
cursor?: opaque string
limit: 1..100 = 50
```

The cursor remains opaque and does not expose database offsets as a public promise.

## 10. Idempotency contract

Durable side-effect operations pass `Idempotency-Key` to `ApiV1Gateway` unchanged.

Persistence uniqueness is provided upstream by NODE-10:

```text
UNIQUE (organization_id, idempotency_key)
```

NODE-20 owns retry/reconciliation implementation.

## 11. Concurrency contract

Mutable resources expose integer `version` values.

Read/create/update responses may return:

```text
ETag: W/"<version>"
```

Update/decision operations parse:

```text
If-Match
```

into the expected entity version and pass it to the application gateway.

Invalid syntax is a stable API problem rather than an ORM exception.

## 12. Async operation contract

Long-running operations return `202 Accepted` once accepted by the application adapter:

```text
createAgentRun
cancelAgentRun
resumeAgentRun
createGeneration
```

A 202 does not mean execution completed.

## 13. Application gateway contract

`ApiV1Gateway` defines async methods for all V1 route behaviors.

Handlers delegate to this Protocol and do not touch database/provider/agent-runtime implementations.

If `app.state.api_v1_gateway` is absent, business routes return:

```text
501 APPLICATION_SERVICE_NOT_INSTALLED
```

This makes missing implementation explicit during contract-first development.

## 14. OpenAPI / TypeScript generation

Implemented scripts:

```text
scripts/export_api_v1_contract.py
scripts/generate_api_v1_client.py
```

Targets:

```text
contracts/api/openapi-v1.json
packages/api-client-v1/src/generated.ts
```

The generator uses Python stdlib + the actual FastAPI OpenAPI document; it adds no separate Node codegen dependency.

The generated files are **not yet claimed current** because the Python dependency environment cannot presently perform the trusted generation/verification step. They must be generated and committed after upstream lock/billing recovery.

## 15. API Contract Gate

`.github/workflows/api-contract.yml` is implemented.

Expected execution after recovery:

```text
uv sync --all-packages --frozen
→ pytest apps/api/tests/test_api_v1_contract.py
→ regenerate OpenAPI
→ regenerate TS operation map
→ git diff/status must remain clean
```

A DTO/route change without regenerated client artifacts will therefore fail.

## 16. Contract tests implemented

`apps/api/tests/test_api_v1_contract.py` covers:

- OpenAPI 3.1;
- all resource paths versioned under `/api/v1`;
- exact operationId set;
- operationId uniqueness;
- tenant header behavior;
- idempotency/concurrency header behavior;
- cursor bounds;
- ProblemDetails schema;
- problem+json validation responses;
- request-ID propagation;
- explicit missing application adapter;
- no ORM/provider/agent-runtime imports in transport package.

## 17. Deliberate non-goals

NODE-11 does not implement:

```text
auth/RBAC
Project business logic
Asset binary upload
Artifact export delivery
Agent orchestration
model execution
streaming/realtime
billing reconciliation
collaboration mutation
```

Those future implementations must plug into the frozen transport/application-service boundary.

## 18. Remaining validation/generation work

Before COMPLETE:

1. fix GitHub Actions Billing & plans / spending limit;
2. generate and commit real upstream `uv.lock`;
3. execute Ruff/Pyright/Pytest on Python 3.12;
4. generate and commit canonical `openapi-v1.json`;
5. generate and commit `api-client-v1/src/generated.ts`;
6. run both generator `--check` modes;
7. run API Contract workflow green;
8. run existing database/contracts/eval/security gates green;
9. wire `install_api_v1` into the production FastAPI composition root when its application gateway is available, without modifying the V1 contract.

Until then:

**NODE-11 engineering status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL.**

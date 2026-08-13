# LUMI AI Design OS — Application Services

> Node: `NODE-13`  
> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Package: `services/application/src/lumi_application`

---

## 1. Purpose

The Application layer owns use-case orchestration and transaction boundaries. It does not own HTTP, SQL, broker, model-provider or agent-runtime implementation details.

```text
HTTP / Agent / Worker adapter
    ↓ command + ApplicationContext
Application Service / Use Case Handler
    ↓
TransactionalExecutor
    ↓
ApplicationUnitOfWork
    ├─ Domain repository ports
    └─ DomainEventOutbox
    ↓
commit or rollback
```

## 2. Dependency rule

Application code may depend on:

```text
Python standard library
lumi_domain contracts
```

It must not depend on:

```text
FastAPI / Starlette
SQLAlchemy / asyncpg / Alembic
LangGraph / LangChain
OpenAI / Anthropic / Google provider SDKs
Redis / RabbitMQ / Celery / S3 adapters
lumi_api implementation modules
```

Concrete adapters point inward toward the Application/Domain ports; Application never imports outward infrastructure.

## 3. ApplicationContext

Immutable use-case context:

```text
organization_id
request_id
correlation_id
actor_id?
trace_id?
```

Rules:

- organization is a trusted application tenant boundary, not inferred from resource ID;
- request ID is transport-independent correlation metadata;
- correlation ID follows one business flow across commands/events;
- actor may be absent for system/internal flows;
- authorization-required use cases must require an actor before policy evaluation.

## 4. ApplicationUnitOfWork

The UoW protocol aggregates Domain repository ports:

```text
projects
assets
artifacts
tasks
agent_runs
cost_ledger
outbox
```

and exposes:

```text
async enter/exit
commit()
rollback()
```

A persistence adapter may bind these repositories and the outbox to one SQL transaction. NODE-10 provides the SQLAlchemy persistence primitives; NODE-13 only defines the orchestration contract.

## 5. TransactionalExecutor

The canonical execution order is:

```text
create UoW
→ enter transaction boundary
→ execute handler
→ validate emitted DomainEvents
→ append events to UoW outbox
→ commit exactly once
→ return value
```

Failure path:

```text
handler error
or event invariant failure
or cancellation
→ rollback
→ re-raise original error
```

The executor catches `BaseException` only to guarantee rollback, then immediately re-raises. It must not swallow cancellation/system-exit style control flow.

## 6. UseCaseResult

Handlers return:

```text
UseCaseResult[T]
  value: T
  events: tuple[DomainEvent, ...]
```

This keeps event staging explicit. A handler does not publish to RabbitMQ.

Before commit the executor verifies:

- every event belongs to the same organization as ApplicationContext;
- one use-case result does not contain duplicate event IDs.

## 7. Domain Event vs Broker Event

NODE-13 stages `DomainEvent` only.

```text
Use Case
→ DomainEvent
→ UoW Outbox adapter
→ NODE-12 envelope mapping / broker publisher later
```

Application code does not construct RabbitMQ exchanges/routing keys or CloudEvents-style broker envelopes.

## 8. Authorization port

`AuthorizationPort` provides an extension point:

```text
require(context, action, resource_type, resource_id?)
```

`require_access()` first requires an authenticated actor and then delegates to the port.

NODE-13 does not define membership/RBAC policy. NODE-16 owns the real authorization adapter and policy model.

## 9. Idempotency port

`IdempotencyPort` exposes application-level coordination primitives:

```text
claim
complete
fail
```

Claim states:

```text
ACQUIRED
REPLAY
CONFLICT
```

`canonical_request_hash()` computes deterministic SHA-256 over canonical JSON with sorted keys and rejects NaN.

`claim_operation()`:

- validates key length;
- delegates durable claim to the port;
- maps request/operation mismatch to `IdempotencyConflict`;
- requires a durable result reference for replay.

NODE-20 owns provider/paid-side-effect reconciliation and concrete retry recovery. NODE-13 only freezes the application-facing port semantics.

## 10. Application errors

Application errors are transport agnostic:

```text
APPLICATION_ERROR
RESOURCE_NOT_FOUND
CONFLICT
ACCESS_DENIED
PRECONDITION_FAILED
IDEMPOTENCY_CONFLICT
APPLICATION_INVARIANT_VIOLATION
```

They do not carry HTTP status codes. NODE-11/adapter mapping converts them to the appropriate Problem Details response.

## 11. Business-service ownership

NODE-13 deliberately does not implement Project/Asset/Artifact/Agent business rules.

Future services use the same executor/UoW pattern:

```text
Project service   -> NODE-17
Asset workflows   -> NODE-26
Agent execution   -> NODE-28+
Auth/RBAC          -> NODE-16
Idempotent paid effects/reconciliation -> NODE-20
Outbox publisher  -> NODE-19
```

This prevents each bounded context from inventing its own transaction/event/error conventions.

## 12. Boundary validation

`scripts/validate_application_boundaries.py` uses Python AST to reject forbidden infrastructure imports and checks the canonical transaction markers remain present:

```text
outbox append
commit
rollback
BaseException rollback path
tenant/event organization check
```

## 13. Test contract

`services/application/tests/test_application_services.py` covers:

- success appends outbox before one commit;
- handler failure rolls back and preserves exception;
- cancellation rolls back and is re-raised;
- cross-tenant event is rejected before commit;
- duplicate event ID is rejected;
- actor-less authorization use case is rejected before policy port call;
- authorization port receives stable action/resource identity;
- idempotency conflicts become transport-agnostic Application errors;
- request hash is canonical and rejects NaN.

## 14. Dependency-light CI

Workflow:

```text
.github/workflows/application-services.yml
```

Requires only:

```text
checkout
Python 3.12
PYTHONPATH to Domain/Application sources
```

Pipeline:

```text
compileall
→ AST boundary validator
→ stdlib unittest
```

It intentionally does not use the stale upstream `uv.lock`.

## 15. Current validation boundary

The only reason this dependency-light gate cannot provide hosted execution evidence is the known GitHub Actions Billing & plans / spending-limit condition that prevents a runner from starting.

Until a real hosted runner executes the gate, NODE-13 remains:

**IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**.

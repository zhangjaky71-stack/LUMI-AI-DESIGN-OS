# NODE-13 Acceptance Report

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Node: **NODE-13 — Application Services**  
> Branch: `node-13-application-services`  
> Stack base: `node-12-event-contract`

---

## 1. Result

NODE-13 has implemented the transport/infrastructure-neutral application-service foundation.

Implemented:

- immutable `ApplicationContext`;
- transport-agnostic Application errors;
- `ApplicationUnitOfWork` Protocol;
- Domain repository port aggregation;
- `DomainEventOutbox` port;
- `TransactionalExecutor`;
- explicit `UseCaseResult[value, events]`;
- cross-tenant DomainEvent guard;
- duplicate event-ID guard;
- rollback on handler error and cancellation;
- AuthorizationPort extension point;
- IdempotencyPort extension point;
- deterministic canonical request hashing;
- dependency boundary validator;
- stdlib async unit tests;
- dependency-light Application Services workflow;
- architecture reference documentation.

## 2. Transaction acceptance contract

Success path is frozen as:

```text
handler
→ validate DomainEvents
→ append outbox entries
→ commit once
→ return result
```

Failure/cancellation path:

```text
rollback
→ re-raise original exception
```

No business event may be emitted after commit by the canonical executor.

## 3. Tenant/event invariant

The executor rejects a DomainEvent whose `organization_id` differs from `ApplicationContext.organization_id` before commit.

One result also cannot stage the same `event_id` twice.

## 4. Dependency boundary

Application code is scanned with Python AST.

Forbidden implementation dependencies include:

```text
FastAPI / Starlette
SQLAlchemy / asyncpg / Alembic
LangGraph / LangChain
provider SDKs
Redis / RabbitMQ / Celery / S3 adapters
lumi_api
```

Only Domain contracts are allowed as an inward LUMI dependency.

## 5. Authorization boundary

`require_access()` requires `actor_id` before delegating to `AuthorizationPort`.

NODE-13 does not implement membership or RBAC rules; that remains NODE-16.

## 6. Idempotency boundary

Application-level primitives include:

```text
ACQUIRED
REPLAY
CONFLICT
```

and canonical SHA-256 request hashing.

Conflict is represented by `IdempotencyConflict`, not an HTTP-specific exception.

Concrete durable storage/reconciliation is delegated to later adapters/NODE-20.

## 7. Tests implemented

Stdlib async tests cover:

- outbox-before-commit ordering;
- single commit on success;
- rollback on exception;
- rollback on cancellation;
- cross-tenant event rejection;
- duplicate event ID rejection;
- actor requirement before authorization;
- authorization delegation;
- idempotency conflict mapping;
- canonical request hash and NaN rejection.

## 8. Dependency-light CI

`.github/workflows/application-services.yml` requires only hosted Python 3.12 plus repository sources.

It does not depend on `uv.lock`, PostgreSQL, FastAPI, SQLAlchemy or provider SDKs.

Expected pipeline:

```text
compileall
→ validate_application_boundaries.py
→ stdlib unittest
```

## 9. External blocker

GitHub hosted runners are still unable to start because GitHub reports the known Billing & plans / Actions spending condition:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased.
```

Therefore no real hosted execution is claimed yet.

## 10. Deliberate non-goals

NODE-13 does not implement:

```text
Project business services
Auth/RBAC policy
Asset upload
Agent orchestration
provider execution
broker publisher
paid-side-effect reconciliation
```

Those later Nodes consume this application boundary.

## 11. Completion gate

NODE-13 can be marked COMPLETE only after:

```text
GitHub Actions billing/spending fixed
+ Application Services workflow gets a real runner
+ compileall PASS
+ boundary validator PASS
+ stdlib tests PASS
+ stacked upstream contract semantics remain consistent
```

Until then:

**NODE-13 engineering status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL.**

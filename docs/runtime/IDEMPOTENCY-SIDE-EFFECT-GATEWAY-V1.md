# Idempotency & Side Effect Gateway V1

Status: **FROZEN FOR NODE-20 IMPLEMENTATION**  
Owner: Runtime Foundation  
Depends on: NODE-10, NODE-15, NODE-19

## 1. Guarantee

LUMI provides an application-level guarantee that one logical business operation does not
silently create duplicate critical side effects when the client retries, a broker redelivers,
a worker crashes, or LangGraph resumes a node.

This is **not** a distributed exactly-once claim. Delivery may occur more than once; the
correctness boundary is the durable operation ledger plus side-effect-specific uniqueness
and provider reconciliation.

## 2. Operations that must use the gateway

The following side effects must be fenced before production activation:

- paid model invocation;
- image generation;
- video generation;
- external tool write;
- object finalization;
- billing charge or credit;
- duplication-sensitive email/invite delivery;
- export creation;
- external publish.

Pure reads do not require an idempotency operation.

## 3. Identity

HTTP commands use `Idempotency-Key`.

The durable uniqueness scope is:

```text
organization_id + operation_type + idempotency_key
```

Internal operations use `deterministic_operation_key()` over:

```text
organization_id
operation_type
business_scope_id
logical business slot
policy version
```

A random retry attempt, worker delivery number, trace ID, request ID, or span ID must not
become part of the business key.

## 4. Canonical request hash

The request hash is SHA-256 of canonical JSON. Object keys are recursively sorted. UUID,
datetime, date, Decimal and Enum values have stable encodings. Non-finite numbers and naive
datetimes are rejected.

The following ephemeral fields are stripped recursively before hashing:

```text
trace_id
traceparent
tracestate
request_id
x_request_id
span_id
retry_attempt
delivery_attempt
```

The same key with a different request hash fails with:

```text
409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST
```

It never returns an unrelated previous result.

## 5. Operation record

NODE-20 evolves the existing NODE-10 `idempotency_operations` table rather than creating a
parallel ledger. `generations.operation_id` therefore remains valid.

The V1 record contains:

```text
id
organization_id
idempotency_key
operation_type
request_hash
business_scope_id
side_effect_kind
compensation_mode
paid
status
lease_owner
lease_expires_at
provider_request_id
result_ref
response_status
response_json
error_category
error_code
error_message
recovery_state
recovery_detail
expires_at
created_at
updated_at
completed_at
version
```

The record is tenant isolated with PostgreSQL RLS.

## 6. State machine

```text
NEW -> IN_PROGRESS -> SUCCEEDED
                  -> FAILED_RETRYABLE
                  -> FAILED_FINAL

FAILED_RETRYABLE -> IN_PROGRESS   # recovery claim
expired IN_PROGRESS -> IN_PROGRESS # recovery claim, new lease
```

`recovery_state` is independent of status:

```text
none
reconciling
ambiguous
```

An ambiguous operation is fail-safe: it is not automatically executed again.

## 7. Claim and lease

Correctness uses the database unique constraint and row lock. Redis may later reduce
contention but may never replace the database constraint.

PostgreSQL acquisition is:

1. set tenant RLS context;
2. `INSERT ... ON CONFLICT DO NOTHING`;
3. if inserted, caller owns the new lease and may execute;
4. otherwise lock the existing row with `SELECT ... FOR UPDATE`;
5. compare request hash;
6. replay terminal success, reject terminal failure, or return WAIT for an active lease;
7. only a retryable/expired record can receive a new recovery lease.

All writes require `organization_id + operation_id + lease_owner`.

## 8. Provider crash window

The critical window is:

```text
provider accepts paid request
-> provider_request_id is persisted
-> process dies before local success commit
```

On lease expiry the next caller must reconcile before another paid call.

Reconciliation results:

- `SUCCEEDED`: converge the provider result into the same operation; do not call provider again.
- `RUNNING`: keep waiting; do not call provider again.
- `NOT_FOUND`: safe re-execution is allowed only when the reconciler can establish that no
  prior provider operation exists. If a previously accepted provider request ID exists but
  status cannot be proven, the operation becomes ambiguous.
- `AMBIGUOUS`: persist ambiguity and require an explicit operator/provider policy decision.

`ambiguous_side_effect_total > 0` is an alert condition.

## 9. Hard crash semantics

A true process kill may occur outside Python exception handling. Therefore the gateway does
not pretend it can always mark failure. The lease remains `IN_PROGRESS`; after expiry,
recovery owns the next decision.

Failure-injection tests use a `BaseException` crash to exercise this exact window.

## 10. HTTP replay

`IdempotentApiService` is a decorator for the current API mutation methods that already
require `Idempotency-Key`:

- create Project;
- create Task;
- create AgentRun;
- cancel AgentRun;
- create Generation command.

The decorator stores an equivalent response payload. Replay reconstructs the same response
model without invoking the inner service again.

`IdempotencyReplayMiddleware` adds:

```http
Idempotent-Replayed: true
```

when the request completed from the operation ledger.

The HTTP generation-create command is only the durable command/write operation. Actual paid
provider execution must have a separate internal side-effect operation so an HTTP request
lease cannot accidentally substitute for provider-call idempotency.

## 11. LangGraph and Worker rule

A graph node must never call a paid provider SDK directly. Any side effect that can happen
before an interrupt must call `SideEffectGateway`. Resume with the same deterministic
business operation key converges to replay/recovery instead of a new charge.

Broker duplicate delivery follows the same rule. NODE-19 Inbox prevents duplicate event
handler effects; NODE-20 fences externally visible/paid effects invoked by worker logic.

## 12. Cost Ledger

NODE-20 adds `cost_ledger.operation_id -> idempotency_operations.id` and the partial unique
index:

```text
UNIQUE (organization_id, operation_id)
WHERE entry_type = 'charge' AND operation_id IS NOT NULL
```

Therefore one logical operation cannot create two charge rows even under racing writers.

Reversal/adjustment is a new append-only ledger entry referencing the old entry. Historical
charge rows are never mutated to simulate compensation.

## 13. Compensation modes

```text
COMPENSATABLE
NON_COMPENSATABLE
REVERSIBLE_BY_NEW_OPERATION
```

The mode documents recovery behavior; it does not magically provide distributed rollback.

## 14. TTL and retention

`ttl_seconds` establishes the replay/retention horizon (`expires_at`). Expiry does **not**
automatically make the same key a new operation. The row may be referenced by Generation,
Cost Ledger, provenance, or audit evidence.

Physical deletion requires a future reference-aware retention/GC policy. Redis TTL is not a
correctness mechanism.

## 15. Metrics

Required counters:

```text
idempotency_replay_total
idempotency_conflict_total
stale_lease_total
provider_reconciliation_total
duplicate_prevented_total
ambiguous_side_effect_total
```

## 16. Database migration

Forward migration:

```text
20260816_0005 -> 20260816_0006
```

It:

- preserves the existing operation IDs and Generation FKs;
- maps `started -> in_progress`, `completed -> succeeded`, `failed -> failed_final`;
- changes uniqueness from `(organization_id, idempotency_key)` to
  `(organization_id, operation_type, idempotency_key)`;
- adds lease/recovery/result/error fields;
- preserves/recreates tenant RLS;
- adds Cost Ledger operation fencing.

Downgrade is fail-closed. If NODE-20 data contains the same client key in more than one
operation type, downgrade raises instead of deleting or silently merging operations that
cannot fit the NODE-10 uniqueness rule.

## 17. Required failure injection

NODE-20 evidence must cover:

- provider success followed by process crash before local completion;
- client timeout and duplicate POST;
- worker/broker duplicate logical operation;
- LangGraph resume using the same deterministic operation key;
- same key with different request hash;
- two concurrent same-key callers;
- stale lease recovery;
- duplicate Cost Ledger charge;
- cross-tenant access rejection.

## 18. Explicit non-claims

NODE-20 does not claim:

- broker exactly-once delivery;
- universal rollback of external systems;
- provider reconciliation support for providers that have not yet been integrated;
- production activation of paid providers before NODE-22 binds them through this gateway;
- safe physical deletion merely because `expires_at` passed.

Next: **NODE-21 — Sandbox Runtime**.

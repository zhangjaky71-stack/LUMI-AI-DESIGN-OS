# Idempotency & Side Effect Gateway V1

> NODE-20 runtime correctness contract.  
> Scope: application-level idempotency, paid side-effect guard, operation leases, response replay, provider reconciliation, and cost-ledger dedupe.

## 1. Guarantee

LUMI guarantees that the same logical command does not silently create a second paid or critical side effect merely because HTTP, LangGraph, Celery, RabbitMQ, or a worker retries execution.

This is **not** a claim of distributed exactly-once delivery. Messages may be delivered more than once. Correctness comes from the PostgreSQL operation record, request hash, unique constraint, provider reconciliation, and side-effect-specific uniqueness.

## 2. Required gateway boundary

The following operations must enter `SideEffectGateway` before execution:

- paid model invocation;
- image/video generation;
- external tool write;
- object finalization;
- billing charge/credit;
- duplicate-sensitive email/invite send;
- export creation;
- external publish.

Pure reads do not need an idempotency operation.

## 3. Identity and request hash

External HTTP calls provide `Idempotency-Key`. Internal workflows derive a deterministic key from business identity, for example:

```text
project_id + task_id + logical_generation_slot + attempt_policy_version
```

Random retry-attempt IDs must not become business keys.

Database uniqueness is:

```text
(organization_id, operation_type, idempotency_key)
```

The canonical request hash sorts object keys and removes transport-only trace/request identifiers. Reusing the same identity with a different semantic request returns `409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`.

## 4. State machine

```text
new
  ↓
in_progress ───────────────→ succeeded
  │                              ↑
  ├─ known safe failure → failed_retryable ─→ new claim
  ├─ known final failure → failed_final
  └─ uncertain outcome ─→ ambiguous
```

`in_progress` owns a bounded DB lease. A concurrent equivalent caller does not acquire another execution right while that lease is active.

## 5. Provider crash window

Critical window:

```text
provider accepted request
→ provider_request_id persisted
→ process crashes before local success commit
```

When the lease expires, the next claimant receives `RECONCILE`, not `EXECUTE`.

- Provider says **succeeded**: adopt the provider result and converge the operation to `succeeded`.
- Provider says **pending**: extend the reconciliation lease and do not execute again.
- Provider says **failed**: clear the old provider request and return `RETRY_SAFE`.
- Provider state is **unknown**: mark `ambiguous`; do not silently spend again.

If a provider has no lookup API, its native idempotency mechanism should receive `OperationHandle.provider_idempotency_key` where supported. Otherwise the ambiguous path is intentionally conservative.

## 6. Response replay

A completed equivalent operation returns the stored `result_ref`, compact `result_json`, and `response_status` without executing the effect again. HTTP adapters may add:

```text
Idempotent-Replayed: true
```

Large result bodies remain in artifact/object storage and are referenced through `result_ref`.

## 7. Cost ledger

`cost_ledger.operation_id` binds a financial entry to the idempotency operation. The unique constraint:

```text
(operation_id, entry_type)
```

prevents the same logical operation from inserting the same charge class twice. A conflicting duplicate with different amount/currency/provider/model raises a ledger conflict instead of silently accepting inconsistent economics.

Reversals are new ledger entries; existing historical charge entries are never mutated into refunds.

## 8. Unknown exceptions

Unknown failures are not automatically treated as retryable for paid work.

- If a provider request ID was already durably bound, the operation remains recovery-eligible but must reconcile before another provider call.
- If no provider request can be proved and execution outcome is uncertain, the operation becomes `ambiguous`.

Callers should raise an explicit `RetryableSideEffectError` only for errors known to be safe before provider acceptance.

## 9. LangGraph and worker rule

A graph node must call the Side Effect Gateway rather than a provider SDK directly when it can create a protected side effect. Interrupt/resume may re-enter node logic, so the deterministic operation key must be stable across resume.

NODE-20 does **not** globally switch Celery to late ACK. Cost-bearing tasks should opt into stronger redelivery only when the concrete provider/tool adapter is routed through this gateway and its reconciliation contract is implemented.

## 10. Compensation

Every protected side-effect kind is classified as one of:

```text
COMPENSATABLE
NON_COMPENSATABLE
REVERSIBLE_BY_NEW_OPERATION
```

Financial reversal and remote-state correction are modeled as new operations rather than mutation of historical evidence.

## 11. Metrics

The gateway emits hooks for:

```text
idempotency_replay_total
idempotency_conflict_total
stale_lease_total
provider_reconciliation_total
duplicate_prevented_total
ambiguous_side_effect_total
```

`ambiguous_side_effect_total > 0` is an operational alert condition once NODE-67 observability wiring exists.

## 12. Failure-injection acceptance

NODE-20 integration tests cover:

1. many concurrent callers using one key;
2. completed client retry / response replay;
3. same key with different request;
4. provider success followed by local crash before commit;
5. provider-confirmed failure allowing a safe retry;
6. unknown provider state blocking retry;
7. duplicate Cost Ledger charge insertion.

Broker duplicate and LangGraph resume reduce to the same deterministic operation identity and are therefore verified through the same claim/replay boundary. NODE-19 remains responsible for transport-level duplicate delivery tests.

## 13. Operational rule

Redis locks may reduce contention but cannot replace the PostgreSQL unique constraint or lease state. The database operation record is the correctness boundary.

## 14. Next node

After NODE-20 gates are green, proceed to NODE-21 — Sandbox Runtime.

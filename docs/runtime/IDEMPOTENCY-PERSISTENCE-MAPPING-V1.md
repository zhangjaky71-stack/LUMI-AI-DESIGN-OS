# NODE-20 Idempotency Persistence Mapping V1

## Baseline

NODE-10 created `idempotency_operations` with `id`, tenant, key, operation type,
request hash, three-state status, optional response JSON and expiry. Generation already
references it through `generations.operation_id`.

NODE-20 intentionally evolves that table in migration `20260816_0006`; it does not create a
second operation ledger and does not rewrite `0001`.

## Forward mapping

| NODE-10 | NODE-20 |
|---|---|
| `started` | `in_progress` |
| `completed` | `succeeded` |
| `failed` | `failed_final` |
| unique `(organization_id,idempotency_key)` | unique `(organization_id,operation_type,idempotency_key)` |
| `response_json` | retained |
| `expires_at` | retained as replay/retention horizon |
| no lease | `lease_owner`, `lease_expires_at` |
| no provider recovery | `provider_request_id`, `recovery_state`, `recovery_detail` |
| no response metadata | `result_ref`, `response_status`, `completed_at` |
| no failure taxonomy | `error_category`, `error_code`, `error_message` |
| no mutable revision | `updated_at`, `version` |

## Cost ledger

`cost_ledger.operation_id` is a nullable FK to `idempotency_operations.id`. A partial unique
index permits at most one `charge` for a given tenant operation. Reversal and adjustment
remain append-only entries and follow the existing `related_entry_id` semantics.

The cost same-tenant trigger is recreated in `0006` so the new operation FK participates in
the same security-definer tenant validation as Project, Task, Generation and ProviderRequest.
The NODE-10 immutable Cost Ledger trigger is never disabled by NODE-20.

## RLS

`idempotency_operations` remains tenant protected using
`lumi_current_organization_id()`. Runtime adapters set that tenant inside each transaction
before INSERT/SELECT/UPDATE. Operation writes also require the expected lease owner where a
lease is active.

## Atomic database side effects

`PostgresTransactionalSideEffectGateway` uses the same PostgreSQL connection and outer
transaction for operation claim, business SQL and operation completion. The business callback
runs inside a savepoint so a normal exception can roll back the business mutation and still
persist a retryable/final operation failure. A hard crash unwinds the outer transaction,
rolling back both the business mutation and its operation claim.

The reference HTTP decorator is not treated as a substitute for this shared-transaction
boundary when the underlying repository commits independently.

## Downgrade

`0006 -> 0005` maps new states back to the NODE-10 three-state contract only when doing so is
lossless.

Before restoring the old unique key it checks for
`(organization_id,idempotency_key)` collisions across operation types. If such rows exist the
downgrade raises; it never deletes or merges one operation to make the old constraint fit.

Downgrade also raises when any Cost Ledger row already has a non-null `operation_id`. Removing
the NODE-20 column in that state would erase append-only billing lineage, so a production
database with operation-bound Cost entries is intentionally not claimed to be losslessly
downgradable to NODE-19.

Only when both guards pass are the Cost Ledger operation FK/index/column removed and the
previous same-tenant trigger restored.

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

## RLS

`idempotency_operations` remains tenant protected using
`lumi_current_organization_id()`. Runtime adapters set that tenant inside each transaction
before INSERT/SELECT/UPDATE.

## Downgrade

`0006 -> 0005` maps new states back to the NODE-10 three-state contract. Before restoring the
old unique key it checks for `(organization_id,idempotency_key)` collisions across operation
types. If such rows exist the downgrade raises. It never deletes one operation to make the
old constraint fit.

The Cost Ledger operation column/index are removed and the previous same-tenant trigger is
restored.

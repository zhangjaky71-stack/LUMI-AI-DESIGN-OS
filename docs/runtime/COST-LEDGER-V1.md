# Cost Ledger V1

> NODE-27 runtime/financial-correctness contract.  
> Depends on NODE-20, NODE-22 and NODE-23.  
> Scope: **provider cost, usage, budget and quota truth**. Customer invoices/subscription billing are not NODE-27.

## 1. Architectural rule

NODE-27 separates five concepts that must never be collapsed into one mutable number:

```text
Estimate
  -> Reservation
  -> Provider side effect
  -> Actual Cost + Usage Facts
  -> optional Adjustment / Reversal
```

A budget reservation is not a cost. An estimate is not a provider charge. A retry is not a new charge unless NODE-20 has proven a new paid side effect occurred.

## 2. Money representation

All cost-domain amounts use `Decimal` in Python and `NUMERIC` in PostgreSQL.

`float` is rejected at the domain boundary. Non-finite numeric values are rejected.

Currency is an explicit three-letter uppercase code. NODE-27 P0 records provider cost in the currency supplied by the pricing snapshot/adapter; no hidden FX conversion is performed.

## 3. Source-of-truth ownership

```text
NODE-20 -> side-effect acceptance, idempotency, ambiguity/reconciliation fence
NODE-23 -> model/pricing snapshot facts
NODE-27 -> immutable provider-cost/usage facts and budget/quota occupancy
NODE-67 -> production dashboards/alerts
```

NODE-27 does not rewrite NODE-20 idempotency records and does not own live provider pricing discovery.

## 4. Cost ledger

`cost_ledger` is an append-only financial fact table.

NODE-27 entry types:

```text
estimate
reservation
actual_cost
adjustment
reversal
```

Production Model Gateway accounting writes `actual_cost`; reservations have their own operational table and are intentionally not duplicated as financial cost rows in the P0 path.

Actual/correction rows are uniquely fenced by:

```text
organization_id + operation_id + entry_type + entry_key
```

The unique fence is backed by replay verification. A duplicate with identical immutable facts replays the existing row; a duplicate with changed amount/provider/model/pricing/provider-request/confidence fails with `COST_LEDGER_OPERATION_REUSED_WITH_DIFFERENT_ENTRY`.

## 5. Immutability

`cost_ledger` and `usage_ledger` have database triggers that reject UPDATE and DELETE.

Corrections therefore use new rows:

```text
actual_cost
   <- adjustment
   <- reversal
```

`reverses_entry_id` ties the correction to its immutable target. An invoice reconciliation is never implemented by updating the original amount.

## 6. Confidence and status

Cost confidence:

```text
exact
estimated
unknown
```

Database insertion normalizes status:

```text
actual + exact      -> final
actual + estimated  -> estimated
actual + unknown    -> unknown
adjustment/reversal -> reconciled
```

Historical pre-NODE-27 `charge` rows are migrated to:

```text
entry_type = actual_cost
confidence = unknown
status = unknown
source = legacy_migration
```

because the historical schema did not preserve enough evidence to truthfully label them exact.

## 7. Pricing provenance

Every new Model Gateway Actual may include:

```text
pricing_snapshot_id
external_provider_request_id
provider
model
```

`pricing_snapshot_id` comes from NODE-23 routing/pricing projection. Historical rate changes therefore do not mutate old cost facts.

The original `provider_request_id UUID` column remains available for LUMI's internal `provider_requests` relation; NODE-27 adds `external_provider_request_id` for the provider-native string identifier.

## 8. Usage ledger

Usage is a separate append-only ledger tied to the cost entry and operation.

Normalized P0 metrics include:

```text
llm.input_tokens
llm.cached_input_tokens
llm.output_tokens
image.generations
video.seconds
provider.requests
```

A usage fact is uniquely fenced by:

```text
organization_id + operation_id + metric + entry_key
```

Cost and usage are inserted in the same PostgreSQL transaction as reservation settlement.

## 9. Model Gateway settlement

The NODE-22 `BudgetPort.settle` contract now includes:

```text
CostEstimate
ModelUsage
provider_request_id
```

The intended runtime order remains:

```text
Router
-> BudgetPort.reserve
-> NODE-20 guarded provider side effect
-> BudgetPort.settle(actual, usage, provider_request_id)
-> non-financial telemetry
```

`Node27BudgetPort` makes `settle()` the only provider-cost writer. `Node27CostTelemetryPort` does not append financial Actual rows, preventing the same provider response from being counted twice.

## 10. Durable reservation recovery

A reservation is a PostgreSQL row. `BudgetReservation.reservation_ref` contains its UUID.

If the process restarts after provider execution, the NODE-27 adapter can reconstruct the reservation handle from `cost_reservations` before settlement. In-memory Python object survival is therefore not required for financial settlement.

## 11. Unknown cost

A provider operation may complete before an exact cost is known.

If no active budget requires a numeric preflight, NODE-27 may preserve the operation as:

```text
amount = 0
confidence = unknown
provider/usage/request provenance = preserved
```

A later reconciler must append an ADJUSTMENT rather than modify the row.

Unknown estimated cost **cannot** bypass an active hard budget. `Node27BudgetPort` fails closed when:

- the request has an operation budget limit but estimate is unknown;
- an applicable persistent hard budget exists;
- an applicable approval-mode budget requires an approval workflow not yet composed.

## 12. Budget model

`cost_budget_limits` supports:

```text
organization
project
agent_run
task
operation
```

and period keys including:

```text
lifetime
month:YYYY-MM
```

Budget reservation is concurrency-safe. `PostgresCostGateway` takes a PostgreSQL transaction advisory lock over the organization budget domain, then evaluates:

```text
settled provider cost
+ active reservations
+ requested estimate
<= limit + tolerance
```

Two concurrent workers therefore cannot both spend the same remaining budget.

`enforcement_mode` supports `hard` and `approval`. The P0 public API does not expose a budget mutation endpoint; reviewed admin control-plane composition remains explicit follow-up work.

## 13. Reservation lifecycle

```text
active
committed
released
expired
```

Same operation/reservation key replay is checked against immutable reservation identity.

- provider success -> commit Actual/Usage and mark reservation committed in the same transaction;
- explicit not-accepted failure -> release reservation;
- TTL expiry -> releases occupancy but does not create a fake cost;
- committed reservation cannot be released.

## 14. Quotas

Money and quantity quotas are separate concepts.

P0 quota metrics include:

```text
provider_cost_usd
image_generations
video_seconds
concurrent_generations
asset_storage_bytes
```

`quota_limits` defines policy. `quota_leases` provides concurrency-safe temporary occupancy for resources such as generation slots/counts.

Quota replay is fenced by organization + operation + metric.

## 15. Tenant isolation

New NODE-27 tables use organization RLS based on:

```text
lumi_current_organization_id()
```

The public read projection starts a transaction and sets:

```text
app.current_organization_id
```

before reading cost/usage aggregates.

Runtime `lumi_app` privileges are intentionally asymmetric:

```text
cost_ledger              SELECT, INSERT; no UPDATE/DELETE
usage_ledger             SELECT, INSERT; no UPDATE/DELETE
cost_reservations        SELECT, INSERT, UPDATE; no DELETE
quota_leases             SELECT, INSERT, UPDATE; no DELETE
cost_budget_limits       SELECT only
quota_limits             SELECT only
cost_budget_change_audit SELECT only
```

Budget/quota definitions are control-plane data and are not mutable through the normal application role.

## 16. Public API

NODE-27 adds read-only endpoints:

```text
GET /api/v1/costs/summary
GET /api/v1/costs/usage
```

The organization comes from the same authenticated organization header/context checked by NODE-16. No cost endpoint accepts a body/query organization override.

The public API intentionally exposes no generic:

```text
POST ledger entry
PATCH amount
DELETE cost
POST adjustment
```

Financial writes are internal service operations or reviewed future admin/reconciliation workflows.

## 17. Migration strategy

Active migration:

```text
20260816_0008
    -> 20260816_0009
```

The migration temporarily removes the cost immutability trigger only inside the migration transaction, evolves historical rows/constraints, then restores immutability.

Downgrade is loss-aware. It is allowed only while the database contains no NODE-27-native usage/reservation/quota/budget/audit data and no new cost rows with `source != legacy_migration`.

If new NODE-27 financial/control facts exist, downgrade raises and preserves the database rather than silently deleting facts.

## 18. Deterministic acceptance

Authored tests/gates cover:

- Decimal precision and float rejection;
- ModelRequest run/generation attribution in semantic identity;
- Model Gateway settlement carries usage/provider request provenance;
- historical `charge` migration;
- migration round trip before new financial facts;
- concurrent reservation overspend prevention;
- Actual + Usage + reservation atomic settlement;
- identical replay without duplicate rows;
- conflicting replay rejection;
- Adjustment and Reversal append-only correction;
- quota lease oversubscription prevention;
- unknown-cost hard-budget fail closed;
- database UPDATE/DELETE rejection;
- `lumi_app` RLS tenant isolation;
- read-only HTTP surface;
- schema/gap/static validation.

## 19. Explicit limitations

See `reports/nodes/NODE-27/gap-ledger.json`.

Most importantly, the reusable `PostgresCostGateway` writer still needs the production tenant-aware connection-pool/service-role composition, and `apps/api` still needs a trusted lock regeneration to formally declare `asyncpg` plus the `lumi-model-gateway` workspace dependency. These are not hidden by manually editing `uv.lock`.

## 20. Next node

After required gates actually execute green: **NODE-28 — Agent Runtime / Orchestration**.

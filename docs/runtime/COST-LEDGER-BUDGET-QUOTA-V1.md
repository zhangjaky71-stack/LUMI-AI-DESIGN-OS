# LUMI Cost Ledger, Budget & Quota Runtime V1

> NODE: 27  
> Phase: 3 — AI Infrastructure  
> Status: IMPLEMENTED / VALIDATING  
> Financial scope: provider cost truth, usage truth, budget reservation, quota guard  
> Customer billing/payment: explicitly out of scope until NODE-63

---

## 1. Purpose

NODE-27 gives LUMI an explainable, durable answer to four different questions:

1. **How much provider cost has actually been incurred?**
2. **How much provider usage produced that cost?**
3. **How much budget is currently occupied by work that may become paid?**
4. **Is a new operation allowed under cost and resource quotas?**

Those questions are intentionally represented by different state models. A temporary budget reservation is not an invoice, an estimate is not an actual cost, and a quota lease is not customer billing.

The node evolves the existing `cost_ledger` introduced in the platform schema. It does **not** create a competing second cost ledger.

---

## 2. Non-negotiable financial invariants

### 2.1 Decimal only

Financial values use Python `Decimal` and PostgreSQL `numeric`.

Floats are rejected at accounting boundaries because binary floating-point cannot provide deterministic financial equality or replay checks.

Provider token counts and quantities are also normalized into non-negative Decimal/numeric facts when written to usage storage.

### 2.2 Financial facts are append-only

`cost_ledger` contains immutable financial facts.

Runtime role `lumi_app` may insert and select rows but NODE-27 explicitly revokes UPDATE and DELETE.

Correction is represented by additional rows:

```text
ACTUAL_COST
+ ADJUSTMENT
+ REVERSAL
= explainable net provider cost
```

An old row is never edited to make history look as if the original observation never happened.

### 2.3 Provider cost is not customer charge

`cost_basis` separates:

```text
provider_cost
customer_charge
```

NODE-27 only produces provider-cost truth. Customer pricing, invoicing, payment collection, tax, credits, refunds and plan billing belong to NODE-63.

A future billing system may derive customer charges from provider cost, but it must not overwrite provider-cost history.

### 2.4 Estimate, reservation and actual are distinct

A provider estimate is routing/planning evidence.

A `cost_reservations` row is transient concurrency-safe budget occupancy.

An `actual_cost` row is immutable financial truth after a paid provider operation has been accepted or otherwise becomes financially attributable.

### 2.5 Every paid fact has an operation identity

NODE-20 `idempotency_operations.id` remains the durable operation identity.

NODE-27 evolves cost uniqueness from:

```text
(operation_id, entry_type)
```

to:

```text
(operation_id, entry_type, entry_key)
```

This preserves exactly-once semantics for one fact while allowing the same operation to have later reconciliation entries.

### 2.6 Historical pricing is frozen by reference

Every actual cost may store `pricing_snapshot_id` from NODE-23 pricing evidence.

A later provider price update does not rewrite historical cost rows.

### 2.7 Sunk provider spend is never erased by budget policy

Budget checks happen **before** provider invocation.

If a provider has already accepted work and an actual result later shows cost greater than estimate, NODE-27 records the actual cost even if this makes the budget negative.

The budget overspend blocks subsequent reservations. It does not make an already incurred provider charge disappear.

---

## 3. Relationship to upstream nodes

### NODE-10 / database foundation

NODE-27 uses PostgreSQL as financial truth and follows the established migration/ORM naming, migration-role and runtime-role boundaries.

### NODE-20 / Idempotency & Side Effect Gateway

NODE-20 owns whether a paid side effect is safe to execute/retry/reconcile.

NODE-27 owns the cost and usage facts that result from that operation.

The same `operation_id` connects the two.

NODE-27 keeps `apps/api/src/lumi_api/idempotency/ledger.py` as a compatibility facade over the evolved `cost_ledger` instead of creating a competing ledger implementation.

### NODE-22 / Model Gateway

Model Gateway remains provider-neutral and DB-neutral.

It receives a `BudgetGuard` and now supports a durable `LedgerBudgetGuard` backed by the DB-neutral `CostAccountingPort`.

Model Gateway does not import asyncpg, SQLAlchemy or PostgreSQL configuration through the new accounting port.

### NODE-23 / Capability Registry

NODE-23 pricing snapshots remain the authoritative versioned pricing evidence.

NODE-27 stores the snapshot identifier used for the cost fact. It does not rewrite or duplicate the capability registry's price database.

### NODE-25 / Tool Gateway

Tool-side write correctness continues to use NODE-20 idempotency through NODE-25. Tool/provider costs can use the NODE-27 accounting port when a paid tool adapter is introduced; NODE-27 does not weaken Tool Gateway authorization or HITL policy.

### NODE-26 / MCP

MCP execution remains behind Tool Gateway. NODE-27 does not allow an MCP server to self-report a trusted financial classification or bypass LUMI cost policy.

---

## 4. Data model

### 4.1 `cost_ledger`

Existing table evolved with:

- `operation_id`
- `entry_key`
- `pricing_snapshot_id`
- `external_provider_request_id`
- `confidence`
- `cost_basis`
- `source`

Important fields:

```text
organization_id
project_id?
task_id?
agent_run_id?
generation_id?
operation_id
provider
model
entry_type
entry_key
amount
currency
pricing_snapshot_id?
external_provider_request_id?
confidence
cost_basis
occurred_at
metadata_json
```

Financial entry types used by NODE-27:

```text
actual_cost
adjustment
reversal
```

Compatibility rows from earlier nodes may contain other entry types; provider-cost summaries intentionally aggregate the NODE-27 financial set only.

### 4.2 `usage_ledger`

Immutable usage facts include:

```text
organization_id
operation_id
cost_entry_id?
project_id?
task_id?
agent_run_id?
generation_id?
provider?
model?
external_provider_request_id?
metric
entry_key
quantity
unit
occurred_at
```

Uniqueness:

```text
(operation_id, metric, entry_key)
```

Supported model usage vocabulary includes:

- input tokens
- output tokens
- total tokens
- cached input tokens
- image input/output tokens
- seconds
- provider-specific unit counters

Future usage types may be added without assuming every provider bills by tokens.

### 4.3 `cost_reservations`

Transient occupancy state:

```text
active
committed
released
expired
```

It stores estimate, provider/model, allocation context, pricing snapshot and expiry.

This table is mutable by runtime because it is coordination state, not financial history.

### 4.4 `cost_budget_limits`

Control-plane policy table.

Scopes:

```text
organization
project
agent_run
task
operation
```

Periods supported in P0 runtime:

```text
lifetime
month:YYYY-MM
```

Runtime role has SELECT-only access. Budget policy mutation belongs to a trusted admin/control-plane path.

### 4.5 `quota_limits`

Control-plane quota policy table.

P0 metrics include:

```text
provider_cost_usd
concurrent_generations
asset_storage_bytes
```

The concrete runtime currently implements lease enforcement for concurrency-like metrics and a read-only quantity hook for externally measured metrics such as Asset storage.

### 4.6 `quota_leases`

Transient quota occupancy with TTL and release timestamp.

It is idempotent by:

```text
organization_id + operation_id + metric
```

---

## 5. Cost confidence

Cost confidence is explicit:

```text
exact
estimated
unknown
```

### Exact

The provider result/price evidence is sufficient to represent the actual amount directly.

### Estimated

The paid operation is known to exist, but the final provider amount is not yet available. NODE-27 records the best available amount as an estimated actual.

### Unknown

Used when the confidence of the fact itself is unknown. Durable budget reservation still requires an amount estimate before new paid work can start.

Unknown/fuzzy actuals must later be reconciled by append-only adjustment rows.

---

## 6. Reservation lifecycle

### 6.1 Normal path

```text
Model Gateway estimates candidate cost
        ↓
LedgerBudgetGuard.reserve
        ↓
PostgresModelCostAccounting
        ↓
PostgresCostGateway.reserve
        ↓
atomic budget check + active reservation
        ↓
NODE-20 protected provider invocation
        ↓
provider result
        ↓
commit actual cost + usage
        ↓
reservation = committed
```

### 6.2 Proven not accepted

When NODE-22 knows the provider did not accept the request:

```text
reservation.release(reason="provider_not_accepted")
```

The reservation stops occupying budget and no actual provider cost is created.

### 6.3 Safe retry

A retry that is proven `NOT_ACCEPTED` remains inside the same candidate reservation.

The provider may be invoked more than once, but the accounting operation still has:

```text
one reservation
one final actual cost
```

NODE-27 unit tests explicitly cover this behavior.

### 6.4 Ambiguous outcome

If delivery state is ambiguous, blind fallback is forbidden by NODE-22.

NODE-27 commits the best available estimate as an estimated actual so financially possible spend is not silently lost.

Later provider reconciliation appends an adjustment if the amount changes.

### 6.5 Reservation TTL

TTL is a coordination timeout, not evidence that a provider did not charge.

An expired reservation stops occupying preflight budget.

A late provider result that proves paid work exists may still commit from `expired` to `committed`.

A reservation explicitly released because the provider was proven not accepted does not accept a normal late commit.

---

## 7. Atomic budget hierarchy

P0 serializes reservation calculations with a PostgreSQL transaction advisory lock:

```text
cost-budget:<organization_id>
```

This deliberately favors correctness over maximum reservation throughput.

Within the lock, NODE-27 evaluates every applicable limit:

```text
organization
project
agent_run
task
operation
```

For each limit:

```text
actual provider-cost facts
+ active unexpired reservations
+ requested estimate
<= amount_limit + tolerance
```

The effective remaining amount is the minimum remaining amount across all applicable limits.

This means a child scope can narrow a parent scope but cannot silently exceed it.

### Why not row-lock budget policy?

`cost_budget_limits` is runtime read-only.

The advisory lock serializes budget calculations without granting `lumi_app` UPDATE permission on policy rows.

---

## 8. Actual cost over estimate

Example:

```text
Task budget:       0.60 USD
Reserved estimate: 0.10 USD
Provider actual:   0.25 USD
```

If the provider has already accepted and incurred 0.25 USD, NODE-27 writes 0.25 USD.

It does **not** fail the financial commit because 0.25 is larger than the estimate.

After the commit, later reservations see the higher actual spend and may fail preflight.

This is required for auditable provider-cost truth.

---

## 9. Adjustment and reversal

Provider invoice reconciliation never mutates the original actual row.

Example:

```text
actual_cost   +0.25000000
adjustment    +0.05000000
reversal      -0.05000000
```

Net provider cost is still explainable from individual facts.

Each correction stores `reverses_entry_id` / target metadata and its own `entry_key`.

Replaying the same correction key with different financial semantics raises a ledger conflict.

---

## 10. Pricing snapshot history

A cost fact stores the NODE-23 pricing snapshot identifier used at the time of accounting.

Example:

```text
pricing_snapshot_id = mock-price-v1
```

Future changes to the model registry do not change this value.

This provides historical explainability even when provider prices later change.

---

## 11. Provider request traceability

There are two request identifiers in the broader schema:

1. internal `provider_requests.id` UUID when a ProviderRequest domain row exists;
2. `external_provider_request_id` for the native provider request/job identifier.

NODE-27 can store the external identifier directly from `ModelResult.provider_request_id` without forcing Model Gateway to know API persistence internals.

This keeps the model runtime DB-neutral while preserving reconciliation evidence.

---

## 12. Model Gateway integration

### `CostAccountingPort`

The Model Gateway-facing contract exposes only:

```text
reserve_provider_cost
commit_provider_cost
release_provider_cost
```

It carries:

- organization
- operation
- project
- task
- AgentRun
- generation
- provider/model
- estimate/actual
- confidence
- pricing snapshot
- provider request ID
- normalized usage

No SQL or database handle crosses this interface.

### `LedgerBudgetGuard`

`LedgerBudgetGuard` implements the existing Model Gateway `BudgetGuard` contract.

It enforces request-local hard budget and delegates durable hierarchy reservation to the cost accounting port.

The old `RequestBudgetGuard` remains available as a non-durable fallback/test boundary; production durable accounting should use `LedgerBudgetGuard`.

---

## 13. Retry and fallback accounting

### Retry on NOT_ACCEPTED

The same candidate keeps its existing reservation.

A successful retry commits once.

### Cross-provider fallback

The failed candidate must be proven safe to release before another candidate reserves its own provider/model cost.

### ACCEPTED / UNKNOWN

Blind cross-provider fallback is prohibited upstream.

NODE-27 therefore does not create two actual provider costs for one logical operation simply because a response was uncertain.

If evidence later proves multiple provider charges really occurred, reconciliation must add separately explainable financial facts instead of hiding them.

---

## 14. Streaming

Streaming has the same financial rule:

- failure before output and proven not accepted → release;
- output emitted or ambiguous provider outcome → preserve possible spend as estimated actual;
- successful stream → commit estimate/available usage.

P0 streaming providers may not expose a final native request ID/cost delta at stream completion; reconciliation can append correction facts when richer provider evidence becomes available.

---

## 15. Quota runtime

### Concurrent generations

`quota_leases` can represent bounded concurrent work.

P0 uses an advisory lock:

```text
quota:<organization_id>:<metric>
```

Only live, unreleased and unexpired leases count toward concurrency.

### Asset storage

Asset storage remains authoritative in NODE-18 storage/asset systems.

NODE-27 exposes a read-only quantity guard:

```text
current_quantity + requested_delta <= quantity_limit
```

The storage system supplies the authoritative current byte count; NODE-27 does not invent a duplicate storage accounting database.

### Provider cost quota

Provider monetary caps should primarily use the budget hierarchy because it includes actual cost + active reservations. `provider_cost_usd` remains part of the quota vocabulary for future policy composition.

---

## 16. HTTP API contract

NODE-27 adds contract routes:

```http
GET /api/v1/usage
GET /api/v1/costs/summary
GET /api/v1/projects/{project_id}/costs
```

All require the existing tenant `RequestContext` boundary.

Time ranges require explicit timezone-aware `from_time` and `to_time`.

### Cost summary response

Includes aggregate values such as:

- actual provider cost
- adjustments
- reversals
- net provider cost
- active reservation amount
- unknown/estimated cost count

The ordinary aggregate API does not expose provider credentials, raw prompts, provider response bodies or native request payloads.

### Usage response

Aggregates quantity by metric and unit.

### Current composition status

The repository's API V1 architecture is still contract-first: a later application-service composition node owns the complete `ApiV1Gateway` implementation for all product endpoints.

NODE-27 therefore validates:

1. the FastAPI/OpenAPI cost contracts;
2. the real PostgreSQL cost summary/usage runtime independently.

It does not claim that every API V1 product route has already been wired to a production application-service composition root.

---

## 17. Access-control model

### Runtime `lumi_app`

Allowed:

- SELECT/INSERT immutable cost facts;
- SELECT/INSERT immutable usage facts;
- SELECT/INSERT/UPDATE transient reservations;
- SELECT budget policy;
- SELECT quota policy;
- SELECT/INSERT/UPDATE quota leases.

Denied:

- UPDATE cost ledger;
- DELETE cost ledger;
- runtime mutation of budget policy;
- runtime mutation of quota policy.

### Migration/admin role

Owns schema/control-plane policy setup and can perform acceptance cleanup.

---

## 18. Failure semantics

### `COST_BUDGET_EXCEEDED`

A new preflight reservation would exceed one applicable budget scope.

### `COST_QUOTA_EXCEEDED`

A new quota lease or quantity delta exceeds configured resource policy.

### `COST_LEDGER_OPERATION_REUSED_WITH_DIFFERENT_ENTRY`

The same operation/entry type/key was replayed with different financial semantics.

### `COST_RESERVATION_CONFLICT`

A reservation replay or lifecycle transition disagrees with the original operation semantics.

### Provider ambiguity

Handled upstream by NODE-20/NODE-22. NODE-27 preserves possible spend instead of guessing that no charge occurred.

---

## 19. Security and privacy

Cost metadata must not become a second prompt/log database.

The accounting contracts reject binary metadata and cap metadata key count/name size.

Normal cost endpoints return aggregates.

Provider credentials never enter accounting contracts.

Prompt/output content is not required for cost truth.

---

## 20. Acceptance model

### Pure contract/unit

- Decimal precision;
- float rejection;
- pricing snapshot preservation;
- allocation context;
- request hard-budget preflight;
- usage normalization;
- unknown actual → estimated actual;
- release idempotency;
- provider retry → one reservation / one actual commit.

### HTTP contract

- OpenAPI includes all three endpoints;
- organization and project scopes propagate;
- aggregate response omits provider-level raw fields;
- invalid time range fails before gateway execution.

### PostgreSQL

The deterministic integration verifies:

- 10 concurrent reservation attempts under a 0.60 task budget produce exactly 6 x 0.10 active reservations;
- releasing one reservation frees exactly one slot;
- actual 0.25 from estimate 0.10 is still recorded;
- overspend blocks later reservations;
- replay does not duplicate actual cost;
- pricing snapshot and provider request ID are retained;
- adjustment/reversal are append-only;
- usage aggregates;
- operation budget narrows parent budgets;
- concurrent generation quota rejects the third live lease;
- Asset storage hook fails closed above limit;
- runtime cannot update/delete cost truth or mutate policy;
- Alembic/ORM schema drift and downgrade/upgrade smoke are clean when the CI database gate can run.

---

## 21. CI gates

Workflow:

```text
.github/workflows/cost-ledger.yml
```

Sequential gates:

### 1. `cost-contract`

- compile financial runtime;
- revalidate NODE-20;
- revalidate NODE-22;
- NODE-27 static financial contract;
- Decimal/domain tests;
- Model Gateway accounting tests.

### 2. `cost-quality`

- frozen `uv` workspace install;
- FastAPI cost API tests;
- Ruff;
- Pyright.

### 3. `cost-postgres`

- start local infrastructure;
- migrate database;
- ORM/Alembic schema check;
- deterministic seed;
- concurrent PostgreSQL cost acceptance;
- downgrade/upgrade smoke.

Hosted success is not claimed until GitHub actually assigns runners and these jobs execute green.

---

## 22. Operational observability hooks

NODE-27 establishes the facts required for later alerts:

- project spend percentage;
- organization monthly spend percentage;
- unknown/estimated actual backlog;
- active reservation value;
- cost spike detection;
- provider/model cost concentration;
- quota saturation.

Alert delivery itself belongs to later observability/product nodes.

Recommended thresholds from the node specification:

```text
50%
80%
100%
```

They are not hard-coded into financial truth.

---

## 23. P0 limitations

The following are intentionally deferred:

1. customer billing/payment/tax/invoice logic;
2. FX conversion snapshots beyond the initial USD provider-cost path;
3. distributed lock optimization finer than organization-level cost advisory lock;
4. automatic provider invoice reconciliation workers;
5. admin UI and write APIs for budget/quota policy;
6. alert delivery;
7. durable application-service composition for every API V1 route;
8. storage-byte metering source of truth, which remains in the Asset/Object Storage layer;
9. sophisticated shared-request cost allocation entries;
10. automatic budget-based quality degradation — hard user quality constraints must never be silently weakened.

---

## 24. Why the P0 advisory lock is acceptable

The organization-level budget advisory lock intentionally serializes reservation decisions within one organization.

Advantages:

- deterministic no-oversell behavior;
- no write privilege on policy rows;
- easy to reason about under concurrent Agent/tool/model work;
- correctness does not depend on cache consistency.

Tradeoff:

- high-volume organizations may eventually need finer-grained locks or an atomic budget service.

That optimization can be implemented behind the same gateway contract without changing immutable ledger semantics.

---

## 25. Financial truth examples

### Successful model call

```text
operation O1
reserve 0.10 USD
provider accepted
actual 0.12 USD
usage: 100 input tokens / 40 output tokens
reservation committed
ledger actual_cost = 0.12
```

### Safe retry

```text
operation O2
reserve 0.10
provider attempt 1: NOT_ACCEPTED
provider attempt 2: success
actual_cost written once
```

### Ambiguous provider outcome

```text
operation O3
reserve 0.20
provider response lost after acceptance is possible
record estimated actual = 0.20
later invoice says 0.23
append adjustment = +0.03
```

### Over-estimate actual

```text
operation O4
reserve 0.10
provider actual = 0.25
write actual = 0.25
remaining budget becomes negative
next paid operation fails preflight
```

### Provider correction withdrawn

```text
actual      +0.25
adjustment  +0.05
reversal    -0.05
net          0.25
```

---

## 26. Definition of Done boundary

NODE-27 implementation is considered code-complete only when the branch contains:

```text
cost ledger evolution
+ immutable usage ledger
+ concurrent durable reservation runtime
+ budget hierarchy
+ quota lease/quantity guards
+ NODE-20 compatibility
+ NODE-22 durable accounting integration
+ HTTP cost/usage contracts
+ deterministic unit/API/PostgreSQL acceptance
+ docs
+ dedicated CI
```

The node must remain:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

until required hosted gates receive real runners and execute green.

After NODE-27, Phase 3 is ready to advance to **NODE-28 — LangGraph Control Plane**.

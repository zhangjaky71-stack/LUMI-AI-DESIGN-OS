# NODE-27 Acceptance — Cost Ledger, Budget & Quota Foundation

> Branch: `node-27-cost-ledger`  
> Base: `node-26-mcp-integration`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Hosted CI: no PASS claimed until the required jobs receive a runner and execute green.

---

## 1. Acceptance scope

NODE-27 is responsible for provider-cost and usage truth, durable preflight budget reservations, reconciliation facts, quota guards and aggregate cost/usage API contracts.

It is **not** customer billing/payment implementation.

The node deliberately evolves the existing platform `cost_ledger` rather than introducing a second competing ledger.

---

## 2. Financial invariants implemented

- [x] Accounting contracts use `Decimal`; explicit float accounting is rejected.
- [x] PostgreSQL financial values use `numeric`.
- [x] Provider cost and future customer charge are separated by `cost_basis`.
- [x] Actual cost, adjustment and reversal are immutable ledger facts.
- [x] Runtime role cannot UPDATE or DELETE `cost_ledger`.
- [x] Usage facts are immutable and idempotent.
- [x] Reservations are transient occupancy, not financial truth.
- [x] Every NODE-27 cost/usage fact is linked to NODE-20 operation identity.
- [x] `pricing_snapshot_id` preserves historical NODE-23 pricing provenance.
- [x] Native provider request/job IDs are preserved as reconciliation evidence.
- [x] Estimate/actual confidence is explicit: exact / estimated / unknown.
- [x] Unknown final provider amount can be recorded from the best estimate and reconciled later through append-only adjustment.

---

## 3. Existing ledger evolution

Migration:

```text
apps/api/alembic/versions/0011_cost_ledger_budget_quota.py
```

The previous NODE-20 uniqueness:

```text
(operation_id, entry_type)
```

is deliberately evolved to:

```text
(operation_id, entry_type, entry_key)
```

This permits an operation to retain one idempotent actual fact and later append separately idempotent adjustments/reversals.

NODE-20 compatibility gateway was updated to continue writing the same `cost_ledger` table.

---

## 4. New persistence surfaces

- [x] `cost_budget_limits`
- [x] `cost_reservations`
- [x] `usage_ledger`
- [x] `quota_limits`
- [x] `quota_leases`
- [x] SQLAlchemy mappings added and exported.
- [x] Runtime/control-plane privileges explicitly narrowed after accounting for 0002 default privileges on future tables.

### Runtime privilege intent

`lumi_app`:

```text
cost_ledger       SELECT + INSERT only
usage_ledger      SELECT + INSERT only
cost_reservations SELECT + INSERT + UPDATE
cost_budget_limits SELECT only
quota_limits       SELECT only
quota_leases       SELECT + INSERT + UPDATE
```

No runtime DELETE on transient cost/quota state is required.

---

## 5. Budget hierarchy

Implemented scope hierarchy:

```text
organization
project
agent_run
task
operation
```

P0 periods:

```text
lifetime
month:YYYY-MM
```

The effective budget is the tightest applicable remaining limit.

A child limit can narrow the parent but cannot expand it.

---

## 6. Concurrent reservation correctness

P0 uses PostgreSQL advisory transaction locking:

```text
cost-budget:<organization_id>
```

The deterministic PostgreSQL acceptance authors the following race:

```text
task budget = 0.60 USD
10 concurrent requests x 0.10 USD
expected successful active reservations = exactly 6
expected active reserved amount = exactly 0.60 USD
```

This is the no-oversell acceptance condition.

One released reservation must immediately free one 0.10 slot for a previously rejected operation.

---

## 7. Sunk-cost correctness

Hard requirement:

> A budget guard may reject new spend before provider invocation, but it must not erase cost already incurred by an accepted provider operation.

Acceptance fixture:

```text
reserved estimate = 0.10 USD
actual provider cost = 0.25 USD
```

Expected:

- [x] actual 0.25 is inserted as financial truth;
- [x] reservation becomes committed;
- [x] later reservation sees the higher spend and is denied;
- [x] no post-accept budget exception rolls back the sunk actual.

Reservation expiry is also treated only as occupancy expiry. A late paid result may commit from `expired`; explicit `released/not accepted` state rejects a normal commit.

---

## 8. Idempotent actual cost

Acceptance fixture commits the same actual twice.

Expected:

```text
first commit  -> inserted=True
second commit -> same entry id, inserted=False
actual row count for operation -> 1
```

A replay with different amount/provider/model/pricing/provider-request/confidence semantics raises a financial conflict rather than silently accepting divergent history.

---

## 9. Usage truth

Actual cost can atomically append normalized usage facts such as:

```text
input_tokens
output_tokens
total_tokens
cached_input_tokens
image_input_tokens
image_output_tokens
seconds
provider-specific units
```

Usage uniqueness:

```text
(operation_id, metric, entry_key)
```

A divergent replay is rejected.

---

## 10. Pricing history

PostgreSQL acceptance stores:

```text
pricing_snapshot_id = mock-price-v1
external_provider_request_id = mock-request-1
confidence = exact
```

and checks the immutable actual row retains those values.

The test does not query a mutable “current price” to reinterpret old spend.

---

## 11. Reconciliation

Acceptance authors:

```text
actual cost       +0.25
adjustment        +0.05
reversal          -0.05
```

Expected:

- [x] correction rows have distinct IDs;
- [x] original actual row remains unchanged;
- [x] adjustment/reversal are append-only;
- [x] summary derives net provider cost from the fact set.

---

## 12. Model Gateway integration

New DB-neutral contract:

```text
CostAccountingPort
```

New durable Model Gateway guard:

```text
LedgerBudgetGuard
```

Production structural adapter:

```text
PostgresModelCostAccounting
```

Integration boundary:

```text
ModelGateway
→ LedgerBudgetGuard
→ CostAccountingPort
→ PostgresModelCostAccounting
→ PostgresCostGateway
```

Model Gateway does not import asyncpg/SQLAlchemy through this boundary.

### Successful result

Model Gateway passes:

- actual `result.cost`;
- `result.usage`;
- native `result.provider_request_id`.

### Safe provider retry

Unit acceptance:

```text
attempt 1 -> RATE_LIMIT / NOT_ACCEPTED
attempt 2 -> success
```

Expected:

```text
paid invocation attempts = 2
budget reservations = 1
actual cost commits = 1
releases = 0
```

This protects against retry double charging in LUMI accounting.

### Ambiguous result

Ambiguous delivery does not blindly release/fallback. The best known estimate is preserved as estimated actual for later reconciliation.

---

## 13. Quota acceptance

### Concurrent generation quota

Fixture:

```text
limit = 2 generations
lease 1 -> allowed
lease 2 -> allowed
lease 3 -> denied
release lease 1
lease 3 -> allowed
```

Only live, unreleased, unexpired leases count.

### Asset storage hook

Fixture:

```text
limit = 1000 bytes
current = 900
+100 -> allowed
+101 -> denied
```

NODE-18 remains authoritative for actual storage quantity; NODE-27 only enforces the supplied trusted quantity against policy.

---

## 14. Runtime privilege acceptance

Separate deterministic script:

```text
scripts/integration_cost_privileges.py
```

It uses `WHERE false` statements so PostgreSQL checks table-level privileges without mutating seeded data.

Expected `InsufficientPrivilegeError` for runtime attempts to:

- UPDATE cost ledger;
- DELETE cost ledger;
- UPDATE usage ledger;
- DELETE usage ledger;
- DELETE cost reservation;
- INSERT/UPDATE/DELETE budget policy;
- INSERT/UPDATE/DELETE quota policy;
- DELETE quota lease.

This specifically protects against broad default privileges configured for tables created by later migrations.

---

## 15. API contract

Added routes:

```text
GET /api/v1/usage
GET /api/v1/costs/summary
GET /api/v1/projects/{project_id}/costs
```

Contract tests verify:

- [x] all paths are present in OpenAPI;
- [x] organization context propagates;
- [x] project scope propagates;
- [x] returned values are aggregate Decimal-backed resources;
- [x] ordinary cost summary does not expose provider/request detail fields;
- [x] timezone-aware range is mandatory;
- [x] invalid range fails before service execution.

Current API V1 is still a contract-first architecture; the complete product application-service composition root is a later node. Real PostgreSQL summary/usage behavior is separately exercised by NODE-27 integration.

---

## 16. Static contract

Validator:

```text
scripts/validate_cost_ledger_contract.py
```

It rejects architectural regressions including:

- missing Decimal/numeric accounting;
- missing provider/customer cost separation;
- missing cost/usage uniqueness;
- missing sunk-cost semantics;
- mutable policy privileges;
- default-privilege leakage;
- DB SDK imports in Model Gateway accounting port;
- policy row-lock requirements that would need runtime UPDATE privilege;
- immutable ledger row locks requiring excess privileges;
- missing API contracts;
- missing concurrency/retry/quota/privilege acceptance fixtures.

NODE-20's static validator is also updated to recognize the deliberate NODE-27 ledger uniqueness evolution.

---

## 17. Test inventory authored

### Pure cost domain

```text
apps/api/tests/test_cost_contracts.py
```

### Cost HTTP contract

```text
apps/api/tests/test_cost_api_contract.py
```

### Model Gateway durable accounting

```text
services/model-gateway/tests/test_cost_accounting.py
```

### PostgreSQL financial behavior

```text
scripts/integration_cost_ledger.py
```

### PostgreSQL privilege boundary

```text
scripts/integration_cost_privileges.py
```

---

## 18. CI

Workflow:

```text
.github/workflows/cost-ledger.yml
```

Sequential required jobs:

1. `cost-contract`
2. `cost-quality`
3. `cost-postgres`

### cost-contract

- compile runtime;
- revalidate NODE-20;
- revalidate NODE-22;
- NODE-27 static financial contract;
- cost domain tests;
- Model Gateway accounting tests.

### cost-quality

- frozen workspace installation;
- cost API tests;
- Ruff;
- Pyright.

### cost-postgres

- infrastructure startup;
- migration upgrade;
- Alembic/ORM schema check;
- deterministic DB seed;
- 10-way concurrent reservation/accounting acceptance;
- runtime privilege acceptance;
- migration downgrade/upgrade smoke.

---

## 19. Validation status discipline

The code, schema, tests, integration harness, docs and dedicated workflow are implemented on the NODE-27 branch.

At the time this acceptance document is authored, **no hosted PASS is claimed**.

The repository has an existing account payment/spending-limit problem that has repeatedly prevented GitHub Actions jobs from receiving runners. NODE-27 must inspect its own workflow run after the Draft PR is opened.

If the required job again shows:

```text
steps=[]
runner_id=0
billing/spending-limit annotation
```

then the status is:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

That condition is not a code/test failure and must not be reported as one.

If a runner starts and a real test fails, the failure is a NODE-27 engineering defect until fixed.

---

## 20. Deferred work

Not claimed in NODE-27:

- customer billing/payment/tax/invoice logic;
- FX conversion snapshots beyond the USD P0 cost path;
- provider invoice reconciliation worker;
- admin budget/quota mutation UI/API;
- alert delivery;
- fine-grained distributed budget service optimization;
- full API V1 application-service composition;
- storage metering source of truth;
- shared-request multi-allocation accounting;
- automatic quality downgrades based on budget.

---

## 21. Definition of Done status

Implemented artifacts satisfy the authored implementation scope:

```text
Cost Ledger
+ Usage Ledger
+ Budget Reservation
+ Budget Hierarchy
+ Quota Foundation
+ NODE-20 compatibility
+ Model Gateway integration
+ Cost API contracts
+ deterministic tests
+ PostgreSQL acceptance
+ privilege acceptance
+ docs
+ CI
```

But **COMPLETE remains false** until the hosted required gates execute green.

Next node after hosted validation: **NODE-28 — LangGraph Control Plane**.

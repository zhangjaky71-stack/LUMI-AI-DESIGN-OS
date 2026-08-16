# NODE-27 Acceptance — Cost Ledger

Status: **IMPLEMENTED / VALIDATING**

## Delivered

- [x] Decimal-only cost domain; float/non-finite values rejected.
- [x] provider-cost vs customer-charge basis is explicit; NODE-27 does not implement billing/invoices.
- [x] Estimate/Reservation/Actual semantics separated.
- [x] immutable `cost_ledger` with `actual_cost/adjustment/reversal` correction model.
- [x] immutable `usage_ledger` tied to operation and cost entry.
- [x] operation + entry type + entry key financial replay fence.
- [x] pricing snapshot provenance from NODE-23.
- [x] external provider request ID provenance.
- [x] Project/Task/AgentRun/Generation/Operation attribution.
- [x] ModelRequest semantic identity includes run/generation attribution.
- [x] Model Gateway BudgetPort settle contract carries usage + provider request ID.
- [x] `Node27BudgetPort` durable reservation and settlement adapter.
- [x] process-restart reservation reconstruction from PostgreSQL.
- [x] telemetry is non-financial; settlement is the sole provider-cost writer.
- [x] unknown-cost Actual representation without mutating historical rows.
- [x] unknown cost fails closed under active hard/operation budgets.
- [x] organization/project/run/task/operation budget scopes.
- [x] lifetime/month period keys.
- [x] PostgreSQL advisory-lock budget concurrency control.
- [x] reservation replay and conflict checks.
- [x] reservation ACTIVE/COMMITTED/RELEASED/EXPIRED lifecycle.
- [x] quota limits and concurrency-safe quota leases.
- [x] append-only Adjustment/Reversal primitives.
- [x] historical pre-NODE-27 `charge` migration to unknown-confidence `actual_cost`.
- [x] cost status normalization trigger.
- [x] loss-aware downgrade guard.
- [x] RLS on usage/budget/reservation/quota/audit tables.
- [x] least-privilege `lumi_app` grants.
- [x] RLS-aware cost/usage read projection.
- [x] authenticated read-only cost/usage API.
- [x] no generic public financial write endpoint.
- [x] ORM metadata updated for evolved and new tables.
- [x] migration `20260816_0009` stacked on `20260816_0008`.
- [x] deterministic contract/unit tests authored.
- [x] PostgreSQL financial/RLS failure-injection suite authored.
- [x] static architecture/financial validator authored.
- [x] contract schema exporter authored.
- [x] dedicated NODE-27 hosted workflow authored.

## Financial invariants authored

The acceptance chain is designed to prove:

1. money uses Decimal/NUMERIC, never float accounting;
2. a NODE-20-era `charge` survives migration without amount loss;
3. migrated rows are not falsely upgraded from unknown evidence to exact/final;
4. two concurrent reservations cannot both consume the same remaining budget;
5. Actual, Usage and reservation settlement are one transaction;
6. identical retry/replay returns the existing financial fact;
7. changed retry semantics fail with a ledger conflict;
8. provider request and NODE-23 pricing snapshot remain attached to the Actual;
9. UPDATE/DELETE on financial facts is rejected by PostgreSQL;
10. reconciliation adds Adjustment/Reversal rows instead of mutating the target;
11. quota leases cannot oversubscribe the configured quantity;
12. unknown cost cannot bypass a hard budget;
13. `lumi_app` sees only the RLS-selected organization;
14. cost API exposes GET projections only;
15. migration downgrade succeeds only before NODE-27-native facts exist;
16. downgrade refuses once new NODE-27 facts/control data would be lost.

## Cross-node boundary

```text
NODE-20 -> paid side-effect acceptance/idempotency/reconciliation fence
NODE-22 -> normalized model result/usage/provider request
NODE-23 -> immutable registry/pricing snapshot provenance
NODE-27 -> immutable provider-cost/usage truth + budget/quota occupancy
NODE-67 -> dashboards/alerts/anomaly monitoring
```

The Model Gateway execution order remains:

```text
route
-> reserve budget
-> NODE-20 guarded paid side effect
-> settle Actual + Usage
-> non-financial telemetry
```

## Public API

```text
GET /api/v1/costs/summary
GET /api/v1/costs/usage
```

There are intentionally no public generic ledger mutation routes.

## Explicit gaps

`reports/nodes/NODE-27/gap-ledger.json` keeps exactly eight gaps visible:

1. `COST-COMPOSITION-001`
2. `COST-PACKAGE-002`
3. `COST-RECONCILE-003`
4. `COST-UNKNOWN-004`
5. `COST-BUDGET-ADMIN-005`
6. `COST-QUOTA-006`
7. `COST-OBS-007`
8. `COST-CI-008`

No standalone lumi-api dependency correctness is claimed until `asyncpg` and the `lumi-model-gateway` workspace edge are formally added and `uv.lock` is regenerated in a trusted environment. No Hosted CI PASS is claimed while no GitHub runner is allocated.

## Required green evidence before COMPLETE

- [ ] frozen workspace sync executes successfully;
- [ ] NODE-27 static validator PASS;
- [ ] cost/model-gateway contract tests PASS;
- [ ] read-only API contract PASS;
- [ ] six exported JSON Schemas validate;
- [ ] exactly eight gaps validate;
- [ ] Ruff PASS on affected scope;
- [ ] Pyright PASS on affected scope;
- [ ] PostgreSQL `0008 -> 0009` historical migration PASS;
- [ ] lossless `0009 -> 0008 -> 0009` pre-fact round trip PASS;
- [ ] financial concurrency/replay/immutability/quota tests PASS;
- [ ] `lumi_app` RLS/privilege test PASS;
- [ ] expected lossy-downgrade refusal after new facts PASS;
- [ ] Hosted Actions receives an actual runner and executes the above steps.

Until those hosted gates execute green, NODE-27 remains **IMPLEMENTED / VALIDATING / not COMPLETE**. If the known repository payment/spending-limit problem persists, classify the run as `BLOCKED_EXTERNAL`, not a source failure.

Next node: **NODE-28 — Agent Runtime / Orchestration**.

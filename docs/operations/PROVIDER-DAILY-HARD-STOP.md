# Provider Daily USD Hard Stop — Production Runbook

> Scope: Final Acceptance closure for the platform-wide provider daily dollar cap.  
> Source control: `apps/api/alembic/versions/0018_provider_daily_cost_hard_stop.py`  
> Runtime path: Model Gateway `LedgerBudgetGuard` → `PostgresModelCostAccounting` → `cost_reservations` → PostgreSQL hard-stop trigger.  
> Time boundary: **UTC day**.  
> Money type: PostgreSQL `numeric(20,8)` / Python `Decimal`; never float.

## 1. Why this control exists

Request-local model budgets do not protect the platform from aggregate denial-of-wallet risk. The production control must stop a paid provider invocation **before provider acceptance** when the platform-wide daily provider allowance would be exceeded, even when requests arrive concurrently from different organizations.

The durable enforcement point is PostgreSQL, not an in-process counter:

```text
Model request
→ durable cost reservation
→ DB provider/day advisory lock
→ committed provider cost + active reservations
→ allow / fail closed
→ only then provider invocation
```

Actual provider cost is immutable truth. If a provider accepts a call and final cost exceeds the estimate, the actual cost is recorded rather than rejected; the shared provider/day lock ensures subsequent admissions observe the larger settled amount and stop.

## 2. Database objects

Migration `0018_provider_daily_cost_hard_stop` adds:

```text
platform_cost_controls
provider_daily_cost_limits
cost_reservations.budget_day_utc
cost_ledger.budget_day_utc
lumi_provider_daily_hard_stop()
lumi_assign_cost_budget_day()
```

`lumi_app` has read-only access to the two policy tables. Runtime code cannot raise or disable limits.

`SECURITY DEFINER` plus `row_security=off` is deliberate: the platform cap must aggregate spend and reservations across every tenant. If PostgreSQL cannot provide the required visibility, the function errors instead of silently enforcing a tenant-local cap.

## 3. Safe activation sequence

The migration creates the control in **disabled** mode so applying a schema migration does not unexpectedly cut off an existing development/staging environment. Production is **not accepted** while it remains disabled.

Configure every paid provider first using the migration/operator database identity. Do not place real provider secrets in these tables.

```sql
BEGIN;

INSERT INTO provider_daily_cost_limits (
    provider,
    amount_limit_usd,
    enabled,
    metadata_json,
    created_at,
    updated_at,
    version
) VALUES
    ('<provider-a>', <daily-usd-limit-a>, true, '{"owner":"<owner>"}'::jsonb, now(), now(), 1),
    ('<provider-b>', <daily-usd-limit-b>, true, '{"owner":"<owner>"}'::jsonb, now(), now(), 1)
ON CONFLICT (provider) DO UPDATE
SET amount_limit_usd = EXCLUDED.amount_limit_usd,
    enabled = EXCLUDED.enabled,
    metadata_json = EXCLUDED.metadata_json,
    updated_at = now(),
    version = provider_daily_cost_limits.version + 1;

UPDATE platform_cost_controls
SET provider_daily_hard_stop_enabled = true,
    updated_at = now(),
    version = version + 1
WHERE id = 1;

COMMIT;
```

Never invent a production dollar amount. The Release Owner and cost owner must choose each cap from provider quota, expected launch traffic, unit economics, and first-day risk tolerance.

To deliberately block a provider, keep the policy enabled and set that provider's `amount_limit_usd` to `0`. Do **not** disable the platform policy as a normal provider-off switch.

## 4. Fail-closed behavior

When `provider_daily_hard_stop_enabled=true`:

- missing provider limit → denied;
- non-USD reservation → denied;
- provider identity missing → denied;
- committed actual + active reservations + requested estimate above cap → denied;
- exact equality with the cap → allowed;
- application/DB accounting failure before reservation → provider call does not start;
- runtime cannot mutate policy tables;
- reservation accounting day is DB-owned and cannot be moved by a caller;
- released/expired reservation reactivation receives the current UTC day;
- actual provider cost inherits the reservation's admission day, including calls crossing UTC midnight.

The application adapter normalizes provider-day DB denials into the existing `BudgetExceeded` contract so Model Gateway surfaces a budget denial instead of a raw PostgreSQL exception.

## 5. Production verification queries

Policy must be on:

```sql
SELECT provider_daily_hard_stop_enabled, updated_at, version
FROM platform_cost_controls
WHERE id = 1;
```

Configured provider caps:

```sql
SELECT provider, amount_limit_usd, enabled, updated_at, version
FROM provider_daily_cost_limits
ORDER BY provider;
```

Today's committed provider cost:

```sql
SELECT provider, budget_day_utc, sum(amount) AS committed_usd
FROM cost_ledger
WHERE cost_basis = 'provider_cost'
  AND entry_type = 'actual_cost'
  AND currency = 'USD'
  AND budget_day_utc = (now() AT TIME ZONE 'UTC')::date
GROUP BY provider, budget_day_utc
ORDER BY provider;
```

Today's active reservations:

```sql
SELECT provider, budget_day_utc, sum(estimated_amount) AS reserved_usd
FROM cost_reservations
WHERE currency = 'USD'
  AND status = 'active'
  AND expires_at > now()
  AND budget_day_utc = (now() AT TIME ZONE 'UTC')::date
GROUP BY provider, budget_day_utc
ORDER BY provider;
```

The operator should reconcile each provider as:

```text
committed actual USD + active reserved USD <= configured daily limit
```

A previously accepted provider call can settle above its estimate. In that case the left side may become greater than the configured limit; this is not corrected by deleting or mutating financial truth. All subsequent admissions for that provider/day must be denied.

## 6. Required automated acceptance

Canonical script:

```bash
PYTHONPATH=apps/api/src:services/model-gateway/src \
uv run python scripts/integration_provider_daily_hard_stop.py
```

It proves:

1. policy-enabled provider with no limit fails closed;
2. four concurrent reservations across two organizations cannot oversubscribe a 0.30 USD provider cap;
3. exact-cap admission succeeds;
4. idempotent replay returns the same reservation;
5. caller cannot tamper `budget_day_utc`;
6. actual cost may exceed the estimate and remains recorded;
7. subsequent provider/day admissions stop after that overshoot;
8. `lumi_app` cannot disable the platform control.

Static contract:

```bash
python scripts/validate_provider_daily_hard_stop.py
```

CI workflow:

```text
.github/workflows/provider-daily-hard-stop.yml
```

The CI workflow deliberately uses canonical Python 3.12, uv 0.11.28 and `uv sync --all-packages --frozen`. It must not bypass a stale root lockfile.

## 7. Production evidence required for NODE-73

Source implementation alone is not Final Acceptance evidence. Archive all of the following against the exact Release Candidate:

```text
migration head includes 0018_provider_daily_cost_hard_stop
platform_cost_controls.provider_daily_hard_stop_enabled = true
all enabled paid providers have explicit USD caps
cross-tenant concurrent acceptance script PASS
missing-provider fail-closed proof PASS
runtime policy mutation negative test PASS
actual-cost overshoot / subsequent-denial proof PASS
UTC day attribution proof PASS
canonical CI PASS
production/staging execution timestamp + release SHA + DB target identity
```

Redact credentials and provider secrets. Dollar limits may be treated as operationally sensitive in externally shared evidence, but the internal release package must preserve enough information to prove the comparison and decision.

## 8. Emergency handling

If the hard stop itself causes an incident, prefer setting a specific provider cap to a reviewed value rather than disabling the platform control. Disabling the singleton policy is a security/cost-control exception and requires an incident/change record, owner, reason, rollback time, and follow-up acceptance rerun.

While the policy is disabled, NODE-73 provider daily hard-stop acceptance is **FAIL / NOT ACCEPTED**, not deferred.

# NODE-24 Acceptance — Provider Health & Circuit Breaker

Status: **IMPLEMENTED / VALIDATING**

Canonical runtime contract: `docs/runtime/PROVIDER-HEALTH-V1.md`  
Persistence mapping: `docs/runtime/PROVIDER-HEALTH-PERSISTENCE-V1.md`

## Implemented

- explicit `UNKNOWN / HEALTHY / DEGRADED / OPEN_CIRCUIT / RECOVERING / DISABLED` state model;
- provider-wide plus model/capability endpoint health scopes;
- bounded rolling success/failure, 429, timeout and latency evidence;
- request latency P50/P95 and queue/poll completion P95 signals;
- minimum sample count, failure-rate thresholds and consecutive-failure OPEN rule;
- explicit Retry-After / capacity-hint handling;
- per-provider/model/capability policy resolver;
- Redis-compatible shared operational store with per-scope distributed lock and TTL;
- Redis failure/reset semantics return `UNKNOWN`, never synthetic HEALTHY;
- atomic RECOVERING probe admission across provider and endpoint scopes;
- Gateway probe gating before provider invocation;
- correct provider-failure attribution; invalid request, user policy, budget, hard-constraint and local/unknown failures do not poison health;
- Router health filtering, conservative UNKNOWN score and DEGRADED/RECOVERING penalty;
- explicit `MODEL_CAPABILITY_TEMPORARILY_UNAVAILABLE` when all viable routes are operationally unavailable;
- fallback/all-unavailable counters for later metrics export;
- strict synthetic probe gate: off by default, terms verified, side-effect-free, cost-limited and no paid probe unless separately enabled;
- probe implementation bugs are not counted as provider failures;
- manual disable / force-degraded / clear-override / clear-breaker with actor, reason, TTL and mandatory audit sink;
- migration `20260816_0008` with append-only health summaries and immutable manual-override audit;
- application role SELECT/INSERT-only grants on NODE-24 history tables;
- dependency-free asyncpg-compatible PostgreSQL persistence adapter;
- real Redis and PostgreSQL integration verification scripts;
- deterministic state-machine, Gateway fallback and synthetic probe unit tests.

## Dedicated hosted gate

`.github/workflows/node-24-provider-health.yml` is designed to execute without any live third-party provider key or public provider call.

The gate must execute:

1. NODE-24 architecture/static validator;
2. Provider Health + Gateway + synthetic probe unit tests and Model Gateway regression;
3. health JSON Schema export/parse validation and exact seven-gap ledger validation;
4. Ruff and Pyright over NODE-24 affected scope;
5. PostgreSQL + Redis local services;
6. `0007 -> 0008` migration;
7. real Redis cross-replica OPEN-state sharing, prefix reset -> UNKNOWN and capacity degradation invariants;
8. PostgreSQL summary/audit append, runtime grants and immutable-audit failure injection;
9. `0008 -> 0007` downgrade proving NODE-23 registry survives and NODE-24 tables are removed;
10. reapply `0008` and rerun persistence invariants.

## Required classification

Do not call NODE-24 COMPLETE until the hosted job receives a real runner and executes its checks. A job with `runner_id=0`, `steps=[]` and the account payment/spending-limit annotation is `BLOCKED_EXTERNAL`, not a source failure and not PASS.

No canonical pytest/Ruff/Pyright/Redis/PostgreSQL/Alembic PASS is claimed from repository state alone.

## Explicit gaps

See `reports/nodes/NODE-24/gap-ledger.json` for the exact seven entries.

NODE-24 closes the runtime health/circuit-breaker requirement at contract/source/persistence-test level. It does **not** claim live provider probes, production-calibrated thresholds, Admin UI/API composition, production Redis client bootstrap, NODE-67 dashboards/alerts, the inherited standalone package edge, or externally blocked Hosted Actions are complete.

Current engineering status: `IMPLEMENTED -> VALIDATING`, with Hosted CI expected to remain `BLOCKED_EXTERNAL` until the GitHub account condition is resolved.

Next engineering node: **NODE-25 — Tool Gateway**.

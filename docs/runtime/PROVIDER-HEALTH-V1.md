# Provider Health & Circuit Breaker V1

Status: **FROZEN FOR NODE-24 IMPLEMENTATION**  
Owner: AI Infrastructure  
Depends on: NODE-22 Model Gateway, NODE-23 Capability Registry

## 1. Responsibility

Provider Health is runtime operational evidence used to decide whether a documented model endpoint should receive traffic **now**. It is not a source of truth for capabilities, pricing, benchmarks, billing, idempotency or artifact provenance.

The routing stack is therefore:

```text
NODE-23 Capability Registry eligibility
+ NODE-24 runtime health/circuit state
+ request/org policy, region and budget
= executable route candidates
```

## 2. Health scopes

Two health scopes are always evaluated:

1. provider-wide transport health;
2. provider + model + capability endpoint health.

A provider-wide timeout/5xx/rate-limit may affect every endpoint. A capability-specific temporary-unavailable error affects only the matching model/capability endpoint. A failing video endpoint must not automatically mark a healthy LLM endpoint unavailable.

## 3. States

Canonical states are:

```text
UNKNOWN
HEALTHY
DEGRADED
OPEN_CIRCUIT
RECOVERING
DISABLED
```

`UNKNOWN` is routable with a conservative score. `DEGRADED` is routable with a penalty. `OPEN_CIRCUIT` and `DISABLED` are excluded. `RECOVERING` is routable only through the bounded probe-admission gate.

`DISABLED` is a manual/policy state. Health observations never auto-clear it. A manual override may have an explicit TTL; expiry is the configured administrative policy ending, not automatic health recovery.

## 4. Circuit breaker

Each scope has a bounded rolling window and provider/capability-resolvable policy:

- window duration and maximum samples;
- minimum sample count;
- degraded/open failure-rate thresholds;
- degraded/open 429 thresholds;
- degraded/open timeout thresholds;
- consecutive-failure OPEN threshold;
- OPEN cooldown;
- RECOVERING success count;
- RECOVERING concurrent probe budget;
- latency P95 degradation threshold;
- queue/poll completion P95 degradation threshold;
- health-state TTL.

The state transition is:

```text
UNKNOWN / HEALTHY / DEGRADED
        │ attributable threshold
        ▼
   OPEN_CIRCUIT
        │ cooldown expires
        ▼
     RECOVERING
        │ bounded probe success(es) ──► HEALTHY
        └ attributable failure ───────► OPEN_CIRCUIT
```

Insufficient samples remain `UNKNOWN`; minimum sample count prevents one incidental observation from declaring the provider healthy or opening it by failure rate. Consecutive failures and explicit `Retry-After` may still open immediately.

## 5. Failure attribution

Only provider/transport-attributable categories become health failures:

```text
rate_limit
timeout
provider_5xx
capability_temp_unavailable
auth_error
provider_unavailable
```

These do **not** poison Provider Health:

```text
invalid_request
user_content_policy_block
budget_exceeded
hard_constraint_invalid
unknown/local implementation error
```

The Model Gateway passes normalized ProviderCallError category, latency and Retry-After evidence into the registry. Local exceptions only release a recovery probe slot.

## 6. Passive signals

The bounded state stores:

- success/failure rate;
- 429 rate;
- timeout rate;
- latency P50/P95;
- queue/poll completion P95;
- consecutive failures;
- capacity hints such as remaining/limit/reset/retry-after.

A capacity hint with zero remaining capacity and a future reset degrades the route. Explicit Retry-After can open the circuit through at least the requested interval.

## 7. Redis operational store

`RedisHealthStateStore` is redis-py compatible but imports no Redis package itself. The host process supplies an authenticated/TLS/pool-configured client.

State mutations are protected by a per-scope distributed lock around load/modify/save so RECOVERING probe admission is atomic across Gateway replicas.

Redis is **not business truth**. If Redis is unavailable or state expires/reset:

```text
health => UNKNOWN
routing => conservative but still possible
billing/idempotency/provenance => unaffected
```

MemoryHealthStateStore is the deterministic reference for tests and single-process development only.

## 8. Router and Gateway integration

`ModelRouter` queries Provider Health with the exact request capability:

- OPEN_CIRCUIT / DISABLED → `health_filtered`;
- DEGRADED → health score penalty;
- UNKNOWN → conservative score;
- RECOVERING → low score and candidate remains probe-gated;
- HEALTHY → normal score.

`ModelGateway` atomically calls `acquire_probe()` before real execution. If the candidate is RECOVERING and no probe capacity is available, it falls back without invoking the provider.

If every viable candidate is health-filtered or recovery-probe-gated, the Gateway raises:

```text
MODEL_CAPABILITY_TEMPORARILY_UNAVAILABLE
```

Provider-attributable failures may trigger normal NODE-22 fallback; paid-side-effect correctness remains guarded by NODE-20 and is not delegated to Health.

## 9. Synthetic probes

Synthetic probes are **off by default**. `SyntheticProbeRunner` embeds no provider SDK and invokes only an injected probe callable after all gates pass:

- global probe policy enabled;
- individual probe enabled;
- provider terms explicitly verified;
- probe marked side-effect-free;
- estimated cost within policy;
- paid probes explicitly allowed when cost is greater than zero;
- recovery probe capacity available.

The default policy has `max_estimated_cost_usd=0` and `allow_paid_probes=false`.

A normalized ProviderCallError/timeout can become health evidence. Probe implementation/configuration exceptions return `probe_internal_error`, release the slot and do not poison provider health.

## 10. Manual overrides

Runtime controls:

```text
disable provider/model endpoint
force degraded
clear override
clear breaker
```

Every manual action requires a non-empty actor, explicit reason and (for override state) bounded TTL. The core registry refuses an override when no audit sink is installed.

The live override is short-lived operational Redis state. Durable override history is append-only PostgreSQL audit. Production Admin orchestration must persist the audit before applying the Redis override; the authenticated API/UI composition is an explicit gap.

## 11. Metrics contract

NODE-24 freezes these metric names/meanings:

```text
provider_success_rate
provider_p95_latency
provider_429_rate
provider_circuit_state
fallback_rate
all_candidates_unavailable_total
```

Health snapshots/transitions, Gateway fallback counters and PostgreSQL summaries provide the source data. Production exporter/dashboard/alert wiring belongs to NODE-67. A critical capability with no available candidate must become an immediate alert there.

## 12. Persistence

Redis stores live rolling windows/circuit state. PostgreSQL stores only append-only operational evidence:

- `provider_health_summaries` — periodic state/metric summary history;
- `provider_health_override_audit` — immutable manual-control audit history.

See `docs/runtime/PROVIDER-HEALTH-PERSISTENCE-V1.md`.

## 13. Security and privacy

Health state and transitions contain provider/model/capability IDs, timing/rate/circuit metrics and operational actor/reason fields only. They do not store prompts, generated outputs, API credentials, provider secrets, raw user content or billing truth.

## 14. Explicit non-claims

NODE-24 does not claim:

- live provider synthetic probes are enabled;
- default thresholds are production-calibrated SLOs;
- production Redis client/TLS/pool bootstrap is frozen in the Model Gateway package;
- Admin UI/API composition is complete;
- NODE-67 dashboards/alerts are complete;
- the inherited standalone API/package lock edge is closed;
- Hosted Actions passed when no runner executed.

Next: **NODE-25 — Tool Gateway**.

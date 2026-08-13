# Provider Health V1

> NODE-24 runtime health and circuit-breaker contract.  
> Depends on NODE-22 Model Gateway and NODE-23 Capability Registry.

## 1. Responsibility

Provider Health is a **runtime operational signal**. It answers whether an installed provider/model is currently healthy enough to receive work.

It must not become a second source of truth for:

- model capabilities, pricing, lifecycle, regions, or benchmark evidence — NODE-23 owns those;
- paid side-effect identity or duplicate prevention — NODE-20 owns those;
- durable Cost Ledger truth — NODE-27 owns that.

The Router combines all three axes:

```text
Capability Registry fact eligibility
+ Provider Health runtime availability
+ request/org budget and policy
= route candidate ordering
```

## 2. State machine

```text
HEALTHY
  │ failure/latency threshold
  ▼
DEGRADED
  │ failure rate or consecutive failures
  ▼
OPEN
  │ cooldown / Retry-After expires
  ▼
HALF_OPEN
  │ limited probe successes        probe failure
  ├──────────────────────────► HEALTHY
  └──────────────────────────► OPEN
```

States are explicit:

```text
healthy
degraded
open
half_open
```

## 3. Sliding evidence window

`AdaptiveProviderHealthRegistry` tracks a bounded provider/model observation window:

```text
success/failure
latency_ms
error_category
monotonic observation time
```

Policy controls:

```text
window_seconds
max_samples
minimum_samples
degraded_failure_rate
open_failure_rate
consecutive_failures_open
open_cooldown_seconds
half_open_successes_to_close
half_open_max_probes
degraded_latency_ms
```

No unbounded request history is retained.

## 4. What counts as Provider failure

Caller/input failures must not poison Provider health.

The reference runtime ignores categories such as:

```text
invalid_request
content_policy
budget_exceeded
cancelled
client_cancelled
```

Infrastructure/provider failures such as timeout, provider 5xx, overload, rate limit, and unknown provider failures affect health.

A rate-limit observation with `Retry-After` may immediately open the circuit through at least that cooldown instead of repeatedly hammering the provider.

## 5. Health score

The health registry exposes a normalized score used by the existing NODE-22 `ProviderHealthRegistry` boundary:

```text
OPEN      -> 0
HALF_OPEN -> low probe score
DEGRADED  -> capped reduced score
HEALTHY   -> score derived from recent failure/latency evidence
```

The score is a routing signal, not a benchmark quality score. NODE-23 quality evidence remains separate.

## 6. HALF_OPEN probe control

After OPEN cooldown expiry, the circuit becomes HALF_OPEN. `acquire_probe` bounds concurrent recovery probes.

A probe result is fed through the same success/failure observation API:

- configured consecutive successful probes close the circuit;
- any Provider failure while HALF_OPEN immediately reopens it;
- a second concurrent probe is denied when the configured probe budget is exhausted.

This prevents a thundering herd immediately after recovery time.

## 7. Telemetry integration

NODE-22 already emits `TelemetryEvent` with:

```text
provider
model
latency_ms
error_category
trace_id
```

`ProviderHealthMonitor` converts those events into health observations and emits `ProviderHealthTransition` only when state changes.

Transition payload includes:

```text
provider/model
previous_state/current_state
score
sample_count
failure_rate
latency_p95_ms
trace_id
error_category
```

Later observability/alerting Nodes can export those transitions without parsing application logs.

## 8. Router integration acceptance

NODE-24 has a deterministic integration test that:

1. compiles the NODE-23 Registry snapshot;
2. chooses two different providers documented for LLM reasoning;
3. registers two NODE-22 MockProvider adapters;
4. drives one provider to OPEN with Provider failures;
5. invokes the real `RegistryAwareModelRouter`;
6. proves the OPEN provider is excluded and the healthy provider is selected.

This proves NODE-22 execution routing, NODE-23 capability eligibility, and NODE-24 runtime health compose through the existing interfaces.

## 9. Process-local vs shared state

Provider health is an operational optimization, not a financial or provenance correctness record. The reference P0 implementation is in-memory and thread-safe so it has no new infrastructure/package dependency.

Multiple Gateway replicas may temporarily have different health observations. That may change route choice but must not break side-effect correctness because NODE-20 still guards paid invocation identity/reconciliation.

For large production fleets, a shared Redis/telemetry aggregation adapter can be added behind the same Provider Health boundary. It must not turn Redis into capability, pricing, benchmark, or billing truth.

## 10. Safety properties

- no Provider credential is stored in health state;
- no prompt/output content is stored;
- client/content-policy failures do not mark Provider unhealthy;
- rate-limit Retry-After is respected;
- OPEN providers receive routing score zero;
- HALF_OPEN probe concurrency is bounded;
- health windows and samples are bounded;
- state transition evidence contains IDs/metrics, not user content.

## 11. Acceptance gates

`Provider Health` workflow runs:

1. revalidate NODE-23 Capability Registry contract;
2. compile health runtime;
3. static ProviderHealthRegistry compatibility validation;
4. deterministic unit state-machine tests;
5. real NODE-23 Registry + NODE-22 Router integration;
6. frozen dependency install;
7. targeted Ruff;
8. targeted Pyright.

Required scenarios include:

- initial HEALTHY;
- invalid-request failure ignored;
- failure-rate DEGRADED;
- consecutive-failure OPEN;
- Retry-After OPEN duration;
- OPEN -> HALF_OPEN;
- one concurrent HALF_OPEN probe;
- successful probes -> HEALTHY;
- failed probe -> OPEN;
- high p95 latency -> DEGRADED;
- Router excludes OPEN provider.

## 12. Next node

After NODE-24 gates are green: **NODE-25 — Tool Gateway**.

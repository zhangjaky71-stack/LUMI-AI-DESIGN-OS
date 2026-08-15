# NODE-69 — Performance, Load & Scalability — Release Evidence

> Evidence date: 2026-08-15  
> Branch: `node-69-performance-scalability-release`  
> Status: **SOURCE IMPLEMENTED / RELEASE BLOCKED**

## Decision

The performance harness source baseline is implemented. This is **not** a claim that launch capacity is green. No production-like Profile G run, Canvas browser benchmark, soak test, failure-under-load exercise, or measured safe-concurrency/cost point has executed in this environment.

## Implemented source baseline

- Versioned A–G workload set: `perf/profiles/v1/`.
- Profile G launch target: 100 connected users, 20 concurrent AI generations, 10 media jobs, 120 SSE connections.
- Canonical profiles use 100% deterministic mock provider / 0% real provider.
- Versioned target budgets with `measured=false`.
- Raw result evidence schema requiring HTTP, resource, DB, queue and AI-latency decomposition.
- Dependency-free contract validator.
- Loopback-only deterministic mock provider.
- Guarded stdlib HTTP load runner; remote targets require explicit enable + exact hostname acknowledgement and redirects are disabled.
- Absolute/regression evaluator; baseline is optional and never fabricated.
- Read-only PostgreSQL performance snapshot; target connection requires explicit acknowledgement and it never installs extensions.
- Capacity/autoscaling plan with safe concurrency intentionally `PENDING` until measurement.
- Performance Contract CI: PR source checks + manual loopback smoke artifact.

## Existing inherited observability reused

NODE-67 browser telemetry already captures TTFB/LCP/INP/CLS plus API/Canvas/route/runtime failures with normalized, bounded labels. NODE-69 treats these as browser diagnostics; it does not stream high-frequency frame samples into general telemetry.

Earlier worker architecture already routes media work to dedicated worker queues; production capacity still requires an actual isolation load test.

## Direct CI evidence

PR #69 head `138c813d52cdeb172628cb58ad91cec81ced12aa` triggered Performance Contract run `31883343538`.

Observed:

```text
source-contract: completed / failure
job id: 95008865704
steps: []
deterministic-local-smoke: skipped (expected for pull_request)
annotation: job was not started because recent account payments failed or the spending limit needs to be increased
```

No checkout, validator, syntax check, or benchmark executed. This is an external GitHub Billing/spending-limit blocker, **not** a performance-test failure. Re-running without fixing Billing would add no engineering evidence.

## Release blockers

- [ ] Performance Contract source job actually executes on a runner.
- [ ] Manual deterministic smoke executes and raw artifact is retained.
- [ ] Profile G production-like launch run completed.
- [ ] API/SSE/DB/Queue evidence captured from the same identified build/environment.
- [ ] Canvas scenarios measured on a frozen reference device/browser.
- [ ] Media pool isolation proven while API/Agent latency remains within accepted budget.
- [ ] Multi-hour soak proves no material RSS/connection/browser/texture growth.
- [ ] Failure-under-load exercises cover provider 429, worker restart, Redis latency, DB failover-equivalent and SSE reconnect storm.
- [ ] Safe concurrency and scaling thresholds replaced from `PENDING` with measured values.
- [ ] Capacity/hour and provider-variable-cost model reviewed using NODE-72 deployment prices.
- [ ] Root `uv.lock` freshness blocker inherited from NODE-66 is resolved and canonical repository gates pass.

## Performance truth rules

1. Budget files are targets, not measurements.
2. Provider latency and LUMI platform overhead are separate dimensions.
3. Local mock smoke validates the harness only; it cannot satisfy launch capacity.
4. A benchmark without profile version, git SHA, environment and provider mode is not release evidence.
5. Raw results must be retained as workflow/report artifacts; fabricated or manually typed performance numbers are invalid.
6. Capacity is declared at a safe operating point with headroom, not at the first saturation/failure point.
7. CPU-only autoscaling is invalid for Agent/Media/SSE workloads; queue age, inflight/backlog and latency are required signals.

## Current status

```text
PERFORMANCE SUITE VERSIONED: YES
TARGET BUDGETS FROZEN: YES (TARGETS ONLY)
DETERMINISTIC MOCK/LOAD TOOLING: IMPLEMENTED
DB SNAPSHOT TOOLING: IMPLEMENTED
AUTOSCALING SIGNAL MODEL: DEFINED
PERFORMANCE CONTRACT RUN: BLOCKED BEFORE RUNNER START (BILLING)
LAUNCH TARGET EXECUTED: NO
CANVAS/SOAK/FAILURE DATA: MISSING
MEASURED CAPACITY/COST: MISSING
NODE-69 RELEASE STATUS: BLOCKED
```

NODE-70 may proceed after this source baseline is preserved, but NODE-69 must not be marked complete until the runtime evidence is captured.

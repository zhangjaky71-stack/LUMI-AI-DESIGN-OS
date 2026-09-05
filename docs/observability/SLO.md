# LUMI AI Design OS — SLO & Error Budget Baseline

Status: NODE-67 baseline  
Window: rolling 30 days unless otherwise stated  
Production owner: Platform / SRE  
Source of truth: version-controlled recording/alert rules plus release evidence

## 1. Principles

SLOs describe user-visible reliability, not whether a process is merely running. Health checks and telemetry-pipeline availability are supporting indicators. A missing telemetry signal is itself an operational incident because it removes evidence, but it must not change the business result of an otherwise successful request.

No SLO is declared PASS until its production/staging signal has been observed and the query has been validated against real traffic. Dashboard existence alone is not evidence.

## 2. Initial SLOs

| SLO | Indicator | Target | Window | Notes |
|---|---|---:|---|---|
| Core API availability | successful eligible requests / eligible requests | >= 99.90% | rolling 30d | Eligible excludes health/metrics endpoints and explicit client 4xx errors |
| Core non-AI API latency | request duration P95 | < 500 ms | rolling 1h and 30d | Route-template aggregation only; never raw IDs |
| Async command acceptance | accepted command latency P95 | < 1 s | rolling 1h | Long-running generation completion is measured separately |
| Realtime event delivery | committed event to client-visible event P95 | < 2 s | rolling 1h | Requires queue/worker/realtime producer metrics before activation |
| Paid side-effect correctness | duplicate paid side effects | 0 | continuous | Any confirmed duplicate is STOP SHIP / incident |
| Cross-tenant isolation | confirmed tenant boundary violations | 0 | continuous | Security invariant inherited from NODE-66 |
| Telemetry pipeline | critical collector/export path availability | >= 99.90% | rolling 30d | Telemetry outage must not fail product operations |

Browser Web Vitals (TTFB/LCP/CLS/INP), route-error rate and Canvas-error rate are currently **diagnostic SLIs**, not production SLOs. They may become user-experience SLOs only after browser telemetry is queryable in the chosen backend, sampling bias is understood, route cardinality/privacy are reviewed, and thresholds are validated against real LUMI traffic/device mix.

## 3. Error budget

For a 99.90% target over a rolling 30-day window, the availability error budget is 0.10%, equivalent to **43 minutes 12 seconds** of bad time if measured purely as time. Request-based SLOs consume budget by bad eligible requests rather than wall-clock time.

Budget policy:

- > 50% remaining: normal release cadence.
- 25–50% remaining: reliability work becomes a release-planning input.
- 0–25% remaining: freeze non-essential reliability-risking changes unless explicitly approved.
- exhausted: reliability incident posture; only fixes, rollback, security emergency work, or approved critical business changes.

A security STOP SHIP condition is not waived by remaining reliability budget.

## 4. Burn-rate alert policy

Production alerting should use multi-window burn-rate rules rather than one fixed 5-minute threshold once enough traffic exists. Initial source-level rules in `infra/observability/prometheus-rules.yml` are bootstrap alerts for local/staging validation and must be replaced or augmented by production burn-rate alerts in NODE-72.

Recommended production classes:

- Fast burn: page when a large fraction of monthly budget can be consumed within hours.
- Slow burn: ticket when sustained degradation would exhaust budget over days.
- Missing telemetry: page/ticket based on whether user-impact diagnosis or release evidence is materially impaired.

## 5. SLI query invariants

1. Never put `organization_id`, `user_id`, `project_id`, `run_id`, raw URL or prompt text into metric labels.
2. Use normalized route templates such as `/projects/{project_id}`.
3. Keep tenant/run/request/correlation identifiers in trace attributes or privacy-safe structured log references.
4. Separate business failures from client errors and cancellations.
5. Provider/model SLI labels must come from bounded registry values.
6. Retry/fallback metrics count attempts and final request outcomes separately.
7. Missing series is not silently interpreted as zero success/failure; dashboards must expose no-data state.
8. Browser SLI aggregation must correct for configured sampling and must not promote request/correlation IDs to metric labels.

## 6. Activation gates

An SLO moves from `DEFINED` to `ACTIVE` only when:

- producer instrumentation exists;
- the metric is scraped/exported in staging;
- label cardinality is reviewed;
- the query is validated against synthetic or controlled traffic;
- dashboard and alert point to a tested runbook;
- owner and escalation route are named;
- data retention supports the target window.

Current NODE-67 source status:

- Core HTTP request count/duration: IMPLEMENTED, execution validation pending.
- Collector/exporter health: CONFIGURED, execution validation pending.
- Provider/model projection: IMPLEMENTED, exporter wiring pending OTel SDK/lockfile work.
- Queue/worker/realtime: trace IDs exist in event envelopes and Worker execution-context binding/reset is implemented; queue/realtime metric exporters remain pending.
- Browser frontend: route/runtime/Canvas errors plus sampled Web Vitals source producer and same-origin intake are implemented; backend aggregation/query remains pending.
- Quality/cost/business SLO signals: contracts/design remain to be connected to canonical engines before activation.

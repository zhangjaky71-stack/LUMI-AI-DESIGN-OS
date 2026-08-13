# NODE-24 Acceptance — Provider Health

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Delivered

- [x] explicit HEALTHY / DEGRADED / OPEN / HALF_OPEN state machine.
- [x] bounded sliding provider/model observation window.
- [x] failure-rate threshold.
- [x] consecutive-failure OPEN threshold.
- [x] latency p95 degradation signal.
- [x] configurable OPEN cooldown.
- [x] rate-limit `Retry-After` cooldown extension.
- [x] bounded HALF_OPEN probe concurrency.
- [x] configurable consecutive probe successes to close.
- [x] HALF_OPEN failure immediately reopens.
- [x] client/input/content-policy failures excluded from Provider health evidence.
- [x] normalized health score for NODE-22 ProviderHealthRegistry routing boundary.
- [x] TelemetryEvent -> health observation monitor.
- [x] structured ProviderHealthTransition event on state changes only.
- [x] no prompt/output/secret persistence in health state.
- [x] deterministic manual-clock unit tests; no sleep-based tests.
- [x] NODE-22 Router + NODE-23 Registry + NODE-24 Health integration harness.
- [x] static ProviderHealthRegistry compatibility validator.
- [x] dedicated contract and frozen-install quality workflow.
- [x] runtime architecture documentation.

## Important boundaries

Provider Health is operational routing evidence only. It does not modify NODE-23 Capability/Pricing/Benchmark facts, does not replace NODE-20 idempotency/reconciliation, and is not Cost Ledger truth.

The reference P0 state is process-local and thread-safe. Replica divergence can affect route choice but must not affect paid-side-effect correctness. A later shared Redis/telemetry aggregation implementation may sit behind the same boundary without changing the business truth model.

## Required green evidence before COMPLETE

- [ ] NODE-23 Registry contract revalidation PASS.
- [ ] Provider Health compile PASS.
- [ ] static ProviderHealthRegistry compatibility PASS.
- [ ] deterministic Provider Health unit suite PASS.
- [ ] real Registry + Router OPEN-provider exclusion integration PASS.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] upstream NODE-23/NODE-22 required gates remain consistent.

The repository currently has a known GitHub Actions account payment / spending-limit blocker. NODE-24 must remain **not COMPLETE** until its hosted jobs actually receive runners and execute. If GitHub again reports `steps=[]` / `runner_id=0`, record that as external infrastructure evidence rather than a product test failure.

Next node: **NODE-25 — Tool Gateway**.

# NODE-22 Acceptance — Model Gateway V1

Status: **IMPLEMENTED / VALIDATING**

Canonical contract: `docs/models/MODEL-GATEWAY-V1.md`

## Implemented

- unified capability-driven ModelRequest/NormalizedResult/stream contracts;
- provider registry and explainable routing by capability, quality, latency, health, region,
  preference and budget;
- provider-local retry separated from cross-provider fallback;
- provider acceptance state (`NOT_ACCEPTED / ACCEPTED / UNKNOWN`) fences paid retries;
- NODE-20 paid-side-effect bridge with durable replay and ambiguity behavior;
- standard budget, health and cost telemetry ports for NODE-27 composition;
- deterministic full-capability MockProvider including image fixture and async video lifecycle;
- OpenAI Responses and Anthropic Messages HTTP adapters without provider SDK leakage;
- Gateway-only secret provider boundary;
- normalized async status/cancel and unpaid stream chunks;
- tests for routing, budget, health, provider payload normalization, fallback safety and NODE-20
  paid failure injection;
- static architecture validator and seven JSON contract schemas.

## Dedicated hosted gate

`.github/workflows/node-22-model-gateway.yml` is intended to execute on Python 3.12 with frozen
workspace dependencies and no real provider keys/network calls.

It runs:

1. architecture/security validator;
2. Model Gateway unit/contract/fallback/provider-adapter tests;
3. NODE-20 paid side-effect bridge tests and idempotency regression;
4. seven schema export/parse checks and gap ledger validation;
5. Ruff and Pyright for NODE-22 scope;
6. provider-secret canary/no-live-key assertions.

## Required classification

Do not call this node COMPLETE until the hosted job actually receives a runner and executes the
above steps. If the job has `runner_id=0` and `steps=[]` with the account billing/spending-limit
annotation, classify it as `BLOCKED_EXTERNAL`, not source failure and not PASS.

## Explicit gaps

See `reports/nodes/NODE-22/gap-ledger.json`. NODE-23 owns the durable capability/model/pricing
registry and NODE-27 owns the financial ledger/reservation truth. Paid streaming, production
secret manager, async poll/webhook orchestration and durable observability remain explicit.

Next engineering node: **NODE-23 — Capability Registry**.

# NODE-22 Acceptance — Model Gateway V1

Status: **IMPLEMENTED / VALIDATING**

Canonical contract: `docs/models/MODEL-GATEWAY-V1.md`

## Implemented

- unified capability-driven ModelRequest/NormalizedResult/stream contracts;
- explainable routing by capability, quality, latency, health, region, preference and budget;
- provider-local retry separated from cross-provider fallback;
- provider acceptance state (`NOT_ACCEPTED / ACCEPTED / UNKNOWN`) fences paid retries;
- NODE-20 paid-side-effect bridge with durable replay and ambiguity behavior;
- budget, health and cost telemetry ports for NODE-27 composition;
- deterministic full-capability MockProvider including async video lifecycle;
- OpenAI Responses and Anthropic Messages adapters without provider SDK leakage;
- Gateway-only secret boundary and JSON-safe durable replay serialization;
- normalized async status/cancel plus unpaid stream health/usage/cost telemetry;
- routing, provider normalization, fallback safety and NODE-20 failure-injection tests;
- static architecture validator and seven JSON contract schemas.

## Dedicated hosted gate

`.github/workflows/node-22-model-gateway.yml` is intended to execute on Python 3.12 with frozen
full-workspace dependencies and no real provider keys/network calls.

It runs architecture/security validation, Model Gateway tests, NODE-20 bridge/regressions, seven
schema checks, eight-gap ledger validation, Ruff, Pyright and provider-secret canary checks.

## Packaging boundary

The API runtime imports `lumi_model_gateway`, but the formal `lumi-api -> lumi-model-gateway`
workspace dependency edge has not been regenerated into the reviewed lock in this environment.
Full-workspace frozen install includes both packages; standalone `lumi-api` package deployment
is explicitly not claimed until a trusted checkout updates `apps/api/pyproject.toml`, regenerates
`uv.lock`, reviews the lock diff and adds a single-package frozen installation gate.

## Required classification

Do not call this node COMPLETE until the hosted job actually receives a runner and executes the
above steps. `runner_id=0` plus `steps=[]` and the account billing/spending-limit annotation is
`BLOCKED_EXTERNAL`, not source failure and not PASS.

## Explicit gaps

See `reports/nodes/NODE-22/gap-ledger.json`. NODE-23 owns durable capability/model/pricing
registry work; NODE-27 owns financial ledger/reservation truth. Paid streaming, production
secret manager, async poll/webhook orchestration, durable observability and the standalone API
package edge remain explicit.

Next engineering node: **NODE-23 — Capability Registry**.

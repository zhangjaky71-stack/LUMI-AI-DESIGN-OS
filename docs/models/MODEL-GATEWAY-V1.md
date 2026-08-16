# Model Gateway V1

Status: **FROZEN FOR NODE-22 IMPLEMENTATION**  
Owner: AI Infrastructure  
Depends on: NODE-20; NODE-23 and NODE-27 complete registry/cost persistence later.

## 1. Purpose

Every model invocation in LUMI crosses one internal boundary. Agent, API, Worker, Sandbox and
domain code express a capability request; they do not import provider SDKs or depend on native
provider response classes.

```text
Caller
  -> ModelRequest
  -> capability / policy router
  -> health + budget guard
  -> ProviderAdapter
  -> provider API
  -> NormalizedResult + Usage + Cost telemetry
```

The V1 runtime is transport-neutral and includes an in-process client. A separate remote service
transport can be added without changing the domain contract.

## 2. Stable request boundary

`ModelRequest` contains organization and logical operation identity, requested capability,
quality/latency profiles, inputs, optional structured-output schema, asset references,
constraints and routing hints.

Callers do not select provider-native parameters. Provider/model preferences are hints and
remain subject to capability, budget, health, region and policy checks.

The semantic request hash excludes request/trace identifiers but includes the logical
`operation_id`. Canonicalization sorts unordered values and rejects NaN/Infinity so retries do
not create accidental semantic identities.

## 3. Capabilities

V1 recognizes reasoning/structured-output/vision LLM calls, image generation/editing,
text/image-to-video, embeddings and document OCR. NODE-23 becomes the durable
Capability/Model/Pricing Registry; NODE-22 keeps the catalog injectable rather than treating
provider tables or today's prices as permanent truth.

## 4. Provider adapter contract

A ProviderAdapter owns `models`, validation, cost estimation, invoke/stream, async status,
cancel and error normalization. Provider secrets and native request/response mapping remain
inside the adapter.

V1 includes OpenAI Responses, Anthropic Messages and deterministic Mock adapters. The Mock
provider covers all NODE-22 capabilities without network access or live provider credentials.

## 5. Routing

`ModelRouter` filters disabled/excluded providers, capability mismatch, quality/latency/region,
health, provider validation, unknown-cost policy and request budget. Accepted candidates and
rejections retain explainable reason codes. Preference bonuses never override hard constraints.

## 6. Retry versus fallback

Provider-local retry and cross-provider fallback are separate. For paid effects the correctness
rule is stricter than the error category:

```text
provider acceptance = NOT_ACCEPTED -> retry/fallback may proceed
provider acceptance = ACCEPTED     -> never call a second paid effect
provider acceptance = UNKNOWN      -> stop and reconcile / mark ambiguous
```

A network timeout is `UNKNOWN`. A 429 is a confirmed rejection and `NOT_ACCEPTED`. Generic 5xx
remains `UNKNOWN` unless a provider-specific adapter can prove the request was not accepted.
This prevents a timeout from becoming two paid generations at two providers.

## 7. NODE-20 paid side-effect bridge

`Node20ModelSideEffectBridge` turns each paid candidate into a durable NODE-20 operation.
Provider/model form candidate identity while the caller's `operation_id` remains the business
scope. Provider request IDs are checkpointed before operation completion and replay returns a
serialized `NormalizedResult` rather than invoking the provider again.

A proven `NOT_ACCEPTED` error is stored with `SIDE_EFFECT_CONFIRMED_NOT_ACCEPTED`; NODE-20 only
uses this recovery exception when no provider request ID exists. All other paid retryable
failures still require reconciliation and become ambiguous when acceptance cannot be proved.

Durable replay serialization recursively converts UUID, Decimal, enum, sequence, mapping and
set-like values into deterministic JSON-safe forms and rejects non-finite or unsupported values.

## 8. Async jobs

Long-running providers may return `PENDING + provider_request_id`. Gateway exposes normalized
`get_async_status` and `cancel`. Mock video exercises `PENDING -> COMPLETED` without provider
credentials. Production poll/webhook scheduling belongs to Worker/Event runtime composition.

## 9. Streaming

Stream chunks are normalized to started/text-delta/usage/completed/error. Unpaid streaming
records final usage, timing, health and cost telemetry. Paid streaming is deliberately
**fail-closed in V1** until provider acceptance and usage can be checkpointed through a
streaming-aware NODE-20 bridge.

## 10. Secrets

Provider credentials are resolved only by Gateway adapters through `SecretProvider`. The
Environment implementation is a local/runtime reference; production secret manager/KMS
rotation remains a separate composition step. Secrets are never ModelRequest/Result/telemetry
or Sandbox fields.

## 11. Cost and budget boundary

NODE-22 estimates candidate cost, reserves through `BudgetPort`, settles/releases a reference
reservation and emits `CostTelemetry`. This is **not** NODE-27 financial truth. NODE-27 owns
PostgreSQL concurrency-safe reservations, immutable actual cost, pricing snapshots, adjustments
and rollups. Real adapter prices are injected rather than frozen in NODE-22 source.

## 12. Provider mappings

OpenAI uses the Responses API mapping, explicitly disables provider-side response storage and
maps JSON Schema structured output. Anthropic uses the Messages API and only advertises
capabilities implemented in V1. Raw provider responses are not returned to callers.

## 13. Observability

Telemetry contains request/candidate/result, fallback index, retry count, provider/model, usage,
cost and timing. Health receives success/failure feedback. Full prompts, raw user image URLs and
provider secrets are not required telemetry fields and must not be logged by default.

## 14. Packaging boundary

`apps/api` now imports the Model Gateway bridge at runtime, but this connector-only environment
cannot safely regenerate and review the complete `uv.lock` after adding the formal
`lumi-api -> lumi-model-gateway` workspace dependency edge. The existing full-workspace frozen
install includes both packages, so NODE-22 validation can exercise the integration, but
standalone `uv sync --package lumi-api` deployment is **not claimed**.

Before production standalone API packaging, a trusted checkout must add the workspace dependency
to `apps/api/pyproject.toml`, run `uv lock`, review the resulting lock diff and then add a
single-package frozen installation gate. This is `MODEL-PACKAGE-008`, not a hidden assumption.

## 15. CI / deterministic mode

MockProvider supplies deterministic reasoning/structured JSON, image refs, async video,
embeddings/OCR, streaming and simulated provider failures. Provider adapter tests monkeypatch
the internal HTTP transport with canary keys; CI never calls public model endpoints.

## 16. Explicit non-claims

NODE-22 does not claim NODE-23 registry persistence, NODE-27 financial persistence, live
provider CI, safe paid streaming, production secret rotation, async provider worker scheduling,
durable observability, standalone `lumi-api` package deployment, or hosted test PASS when GitHub
assigned no runner.

Next: **NODE-23 — Capability Registry**.

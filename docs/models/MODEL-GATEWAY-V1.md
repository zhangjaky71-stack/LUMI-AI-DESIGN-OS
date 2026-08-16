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

V1 recognizes:

- `llm.reasoning`, `llm.structured_output`, `llm.vision`;
- image generate/edit/mask/reference-consistency/transparent-background;
- text-to-video and image-to-video;
- text/multimodal embeddings;
- document OCR.

NODE-23 becomes the durable Capability/Model/Pricing Registry. NODE-22 deliberately keeps the
catalog injectable rather than treating hard-coded provider tables or today's prices as
permanent truth.

## 4. Provider adapter contract

A ProviderAdapter owns:

```text
models()
validate(request, model)
estimate_cost(request, model)
invoke(request, model)
stream(request, model)
get_async_status(provider_request_id, model)
cancel(provider_request_id, model)
normalize_error(error)
```

Provider secrets and provider-native request/response mapping stay inside the adapter.

V1 includes:

- `OpenAIResponsesAdapter` for reasoning, structured output and vision;
- `AnthropicMessagesAdapter` for reasoning and vision;
- deterministic `MockProvider` for all CI capabilities including image/video/embedding/OCR.

No live provider key is required by CI.

## 5. Routing

`ModelRouter` produces an ordered and explainable candidate list. It filters:

1. disabled/excluded providers;
2. capability mismatch;
3. quality threshold;
4. latency threshold;
5. region mismatch;
6. unhealthy provider/model;
7. adapter validation failure;
8. unknown cost when policy forbids it;
9. request budget overflow.

Each accepted candidate has `reason_codes`; rejections are also recorded. Preference bonuses do
not override hard capability, quality, region, health or budget filters.

## 6. Retry versus fallback

Provider-local retry and cross-provider fallback are different mechanisms.

Fallback taxonomy permits rate limit, timeout, provider 5xx and temporary capability
unavailability in principle. Auth errors, invalid requests, user policy blocks, budget failures
and hard constraint failures do not fallback.

For paid effects there is an additional correctness rule:

```text
provider acceptance = NOT_ACCEPTED -> retry/fallback may proceed
provider acceptance = ACCEPTED     -> never call a second paid effect
provider acceptance = UNKNOWN      -> stop and reconcile / mark ambiguous
```

A generic network timeout is `UNKNOWN`, because the request may have reached the provider.
A 429 is an explicit rejection and is `NOT_ACCEPTED`. Generic 5xx remains `UNKNOWN` unless a
provider-specific adapter can prove the request was not accepted.

This rule is stricter than error taxonomy alone and prevents a timeout from becoming two paid
generations at two providers.

## 7. NODE-20 paid side-effect bridge

`Node20ModelSideEffectBridge` converts a paid candidate into a durable NODE-20 operation.
Provider/model are part of candidate identity while the caller's logical `operation_id` remains
the business scope.

When the provider returns an ID, it is checkpointed before operation completion. Replay returns
a serialized `NormalizedResult`, not a second provider invocation.

A provider error proven `NOT_ACCEPTED` is stored with
`SIDE_EFFECT_CONFIRMED_NOT_ACCEPTED`. NODE-20 recognizes that marker only when no
`provider_request_id` exists and allows safe recovery. Other paid retryable failures still
require reconciliation and become ambiguous when acceptance cannot be established.

## 8. Async jobs

Long-running providers may return `PENDING + provider_request_id`. Gateway exposes normalized
`get_async_status` and `cancel` entry points. Mock video exercises `PENDING -> COMPLETED` without
provider credentials.

Production poll/webhook scheduling belongs to the Worker/Event runtime composition. Model
Gateway only owns provider normalization.

## 9. Streaming

LLM stream chunks are normalized to `started`, `text_delta`, `usage`, `completed`, `error`.
Provider-specific event classes never escape the Gateway.

Paid provider streaming is intentionally **fail-closed in V1** until the streaming transport can
checkpoint provider acceptance and usage through NODE-20. Mock/unpaid streaming is executable
for contract tests. This is a safety limitation, not a claim of completed paid streaming.

## 10. Secrets

Provider credentials are resolved only in Gateway adapters through `SecretProvider`.
`EnvironmentSecretProvider` is a local/runtime reference; production secret manager/KMS
rotation is a separate composition step.

Secrets are never fields on `ModelRequest`, `NormalizedResult`, telemetry or Sandbox specs.
NODE-21 sandbox therefore has no reason to receive long-lived provider keys.

## 11. Cost and budget boundary

NODE-22 can estimate candidate cost, reserve through `BudgetPort`, settle/release a reference
reservation and emit `CostTelemetry` with normalized usage/cost.

This is **not** the NODE-27 financial truth. NODE-27 owns PostgreSQL concurrency-safe budget
reservation, immutable actual-cost entries, pricing snapshots, adjustments and rollups.
Prices in real adapters are injected; NODE-22 does not freeze today's public provider prices in
source code.

## 12. Provider mappings

OpenAI adapter uses the Responses API mapping and explicitly disables provider-side response
storage in its request. Structured-output requests are formatted as provider JSON Schema
output. Anthropic uses the Messages API contract and only advertises capabilities implemented
and tested in V1; it does not claim structured output merely to increase coverage.

Raw provider responses are not returned to callers. A future restricted `raw_response_ref` may
point to controlled debug evidence, subject to data-retention policy.

## 13. Observability

The normalized telemetry boundary contains request/candidate/result, fallback index, retry
count, model/provider, usage, cost and timing. HealthPort receives success/failure feedback.

Full prompts, raw user image URLs and provider secrets are not required telemetry fields and
must not be logged by default.

Durable metrics/traces, redacted raw-response storage and alerting are production composition
gaps, not hidden inside request models.

## 14. CI / deterministic mode

MockProvider supplies deterministic:

- reasoning and structured JSON;
- image fixture refs;
- async video lifecycle;
- embeddings and OCR;
- normalized streaming;
- simulated rate-limit/timeout/5xx behavior.

Provider adapter tests monkeypatch the internal HTTP transport and use canary keys. CI never
calls public model endpoints and never requires real provider credentials.

## 15. Explicit non-claims

NODE-22 does not claim:

- NODE-23 persistent model/capability/pricing registry is complete;
- NODE-27 financial ledger/reservation is complete;
- live provider requests are part of CI;
- paid provider streaming is safe before a checkpoint-aware streaming bridge exists;
- production secret manager rotation is wired;
- async provider webhook/poll workers are wired;
- hosted tests passed while GitHub assigned no runner.

Next: **NODE-23 — Capability Registry**.

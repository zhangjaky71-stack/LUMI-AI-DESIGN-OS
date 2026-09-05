# Model Gateway V1

> NODE-22 / Phase 3 AI Infrastructure  
> Priority: P0 / CORE  
> Scope: provider-neutral model request/result contract, routing, fallback, retry, paid-side-effect guard, usage/cost telemetry, MockProvider, and initial OpenAI Responses adapter.

## 1. Boundary

Every LUMI LLM, image, video, embedding, and OCR model operation must enter the Model Gateway. Agent Runtime, API, Worker, Sandbox, and Tool Gateway must not import provider SDKs or read provider API keys directly.

The caller asks for a capability. It does not construct a provider-native request.

```text
Caller
  -> ModelRequest
  -> Capability / policy / health / budget router
  -> ordered RouteCandidate[]
  -> NODE-20 paid invocation guard
  -> ProviderAdapter
  -> normalized ModelResult / StreamChunk
  -> usage + cost + telemetry
```

Provider secrets remain inside the Gateway adapter scope.

## 2. ModelRequest

The frozen request identity includes:

```text
request_id
organization_id
project_id?
task_id?
operation_id
capability
quality_profile
latency_profile
budget_limit_usd?
inputs
structured_output_schema?
reference_assets[]
constraints
routing_hints
trace_id?
```

`operation_id` is mandatory because paid model execution is a NODE-20 protected side effect.

`routing_hints` is intentionally narrow:

```text
preferred_provider
preferred_model
allow_fallback
```

Provider/model preferences are soft scoring hints, not policy bypasses. A preferred provider still has to satisfy capability, quality, latency, health, organization, region, and budget checks.

## 3. Capability vocabulary

NODE-22 freezes the initial capability names:

```text
llm.reasoning
llm.structured_output
llm.vision
image.generate
image.edit
image.mask_edit
image.reference_consistency
image.transparent_background
video.text_to_video
video.image_to_video
embedding.text
embedding.multimodal
ocr.document
```

NODE-23 moves provider/model capability data into the durable Capability Registry. The NODE-22 in-memory registry is a runtime bootstrap implementation only.

## 4. ProviderAdapter

Every adapter implements:

```text
descriptor
validate(request)
estimate_cost(request)
invoke(request)
stream(request)
get_async_status(provider_request_id)
cancel(provider_request_id)
normalize_error(error)
```

Provider-native classes do not escape this adapter.

`ProviderModel` declares provider/model identity, supported capabilities, quality score, latency class, regions, streaming support, and async support.

An adapter must only advertise capabilities it actually implements.

## 5. Routing

`ModelRouter` filters each adapter by:

1. required capability;
2. minimum quality profile;
3. latency profile;
4. organization allow/deny policy;
5. model deny policy;
6. requested/organization region policy;
7. provider health;
8. provider validation;
9. estimated budget.

Each accepted candidate records explainable reason codes such as:

```text
CAPABILITY_MATCH
QUALITY_THRESHOLD_MET
LATENCY_PROFILE_MET
PROVIDER_HEALTHY
POLICY_ALLOWED
BUDGET_ALLOWED
PREFERRED_PROVIDER
PREFERRED_MODEL
```

Rejected candidates retain rejection reason codes for debugging and observability.

Candidate score combines quality, latency, estimated cost, and preference bonuses. Policy checks are never converted into score penalties; violations are hard rejections.

## 6. Fallback safety

Error category and delivery state are separate dimensions.

Normalized categories include:

```text
RATE_LIMIT
TIMEOUT
PROVIDER_5XX
CAPABILITY_TEMP_UNAVAILABLE
AUTH_ERROR
INVALID_REQUEST
USER_CONTENT_POLICY_BLOCK
BUDGET_EXCEEDED
HARD_CONSTRAINT_INVALID
PROVIDER_UNAVAILABLE
UNKNOWN
```

Delivery state is:

```text
NOT_ACCEPTED
ACCEPTED
UNKNOWN
```

Cross-provider fallback is permitted only when:

```text
category is fallbackable
AND delivery_state == NOT_ACCEPTED
```

This is deliberately stricter than “timeout/5xx means retry.” A timeout or 5xx can occur after a paid provider accepted work. If acceptance cannot be disproved, the Gateway returns `MODEL_PROVIDER_OUTCOME_AMBIGUOUS` rather than silently spending again at another provider.

The same rule applies to provider-local retry.

## 7. Provider retry

Provider-local retry is separate from cross-provider fallback.

`RetryPolicy` bounds:

```text
max_attempts_per_provider
base_delay_seconds
max_delay_seconds
max_elapsed_seconds
```

`Retry-After` is honored within the configured maximum delay. Retry is allowed only for a retryable error whose delivery state is `NOT_ACCEPTED`.

`allow_fallback=false` restricts the Gateway to the primary route after routing is complete.

## 8. NODE-20 idempotency boundary

`ModelGateway` cannot be constructed without `PaidInvocationGuard`.

This is an architectural guardrail: every provider invocation passes through a NODE-20-compatible paid-side-effect boundary before adapter execution.

The model-gateway package does not import `apps/api` or a concrete database implementation. The composition root must adapt the NODE-20 `SideEffectGateway` to the `PaidInvocationGuard` port. This preserves service dependency direction while making the paid guard mandatory.

CI uses `InMemoryIdempotentPaidInvocationGuard` to prove the required semantics:

```text
same organization + operation_id + semantic request
-> concurrent duplicate calls
-> one provider invocation
-> one replayed normalized result
```

Production still uses the durable NODE-20 database lease/reconciliation implementation.

## 9. Request semantic hash

`ModelRequest.semantic_hash` hashes business semantics and excludes transport-only request/trace identity.

Telemetry uses this hash rather than storing raw prompt or reference assets.

The paid guard may use it to detect illegal reuse of one logical operation with different model semantics.

## 10. Budget

Routing estimates cost before invocation.

When a hard request/organization budget exists:

- unknown estimated cost fails closed;
- estimate above the smallest applicable limit is rejected;
- an accepted route obtains a `BudgetReservation` before provider execution;
- successful/ambiguous accepted work commits the reservation;
- proven-not-accepted failures release it.

NODE-22 ships `RequestBudgetGuard` as the local boundary. NODE-27 can replace it with durable quota/cost-ledger reservation without changing `ModelGateway`.

## 11. Cost and usage

Adapters return normalized `Usage` and `CostEstimate`.

Cost confidence is:

```text
EXACT
ESTIMATED
UNKNOWN
```

Price data is represented by `PriceCard` and `price_snapshot_id`. The OpenAI adapter does not hardcode a supposedly current price. Deployment supplies a versioned price snapshot/rates; if rates are absent, cost remains `UNKNOWN` rather than fabricating precision.

For token-based models the adapter can turn actual input/output usage into exact cost relative to the configured price snapshot.

## 12. Telemetry

`TelemetryEvent` records:

```text
request_id
organization_id
operation_id
capability
provider/model
routing_reason_codes
attempt
fallback_index
retry_count
latency_ms
usage
cost
error_category
semantic_hash
trace_id
```

It does not contain raw prompt, user image URLs, or reference asset contents.

## 13. Streaming

Gateway streaming returns normalized `StreamChunk`:

```text
request_id
provider/model
sequence
kind
delta?
usage?
finish_reason?
```

A separate `PaidStreamGuard` is mandatory for streaming so a caller cannot bypass the paid-side-effect boundary by choosing a stream API.

Once any provider chunk has been emitted, cross-provider fallback is forbidden because the provider has necessarily begun producing externally visible work.

The NODE-22 MockProvider implements streaming for deterministic CI. The initial OpenAI adapter intentionally does not claim streaming support until a streaming transport is implemented and tested.

## 14. Async image/video lifecycle

Adapters can return:

```text
status=PENDING
provider_request_id=<opaque provider id>
```

Caller/worker then uses `get_async_status`. Cancellation uses the same provider/model identity and opaque request ID.

MockProvider implements deterministic async video: queue -> pending -> completed, plus cancellation.

Provider-specific polling/webhook convergence remains behind the adapter.

## 15. MockProvider

MockProvider is a full deterministic integration provider and requires no credential.

It supports:

- deterministic LLM text;
- deterministic JSON-schema-shaped structured output;
- fake image asset refs;
- async fake video;
- embedding fixtures;
- OCR-shaped text result;
- normalized streaming chunks;
- injected 429/timeout/5xx/other errors with explicit delivery state.

All CI acceptance must be runnable without a live provider key.

## 16. Initial OpenAI Responses adapter

NODE-22 ships one real provider adapter using the server-side OpenAI Responses HTTP API without the OpenAI SDK.

The adapter currently advertises only:

```text
llm.reasoning
llm.structured_output
```

It deliberately does not claim image/video/streaming capabilities that this adapter version has not implemented.

Security/data defaults:

- `OPENAI_API_KEY` is read only inside Model Gateway adapter construction;
- authorization header never appears in adapter repr/result/telemetry;
- Requests payload sets `store=false` by default;
- caller inputs accept provider-neutral prompt/messages only;
- unknown/provider-native message fields are rejected;
- standard Responses `output[]` message/content items are parsed directly;
- raw provider JSON is not returned to callers.

Price rates are deployment configuration, not source-code constants.

## 17. Health

NODE-22 provides an in-memory health registry with a failure threshold and cooldown.

Only transport/availability classes affect health. Invalid requests/auth/policy failures do not poison provider health.

NODE-23/observability nodes may replace this with distributed health data later.

## 18. Secret boundary

Provider SDK imports and provider API key reads are prohibited in:

```text
apps/api
apps/agent-runtime
apps/worker-media
services/sandbox-runtime
services/tool-gateway
```

`validate_model_gateway_contract.py` parses those Python sources and fails CI if known provider SDK modules or provider credential names appear.

Provider credentials belong only to adapter composition inside Model Gateway scope.

## 19. Verification

Fast contract gate:

```bash
make model-gateway-contract
```

It runs:

```text
static architecture/secret scan
stdlib unit suite
mock full integration
```

Hosted NODE-22 workflow additionally runs frozen workspace install, Ruff, and Pyright.

No live OpenAI key is required for NODE-22 acceptance. The OpenAI adapter is exercised through a deterministic fake HTTP transport that verifies wire payload/result/error normalization.

## 20. Definition of Done

NODE-22 is complete only when:

```text
provider-neutral API/client committed
+ mandatory paid guard proven
+ MockProvider full CI green
+ real OpenAI adapter fake-transport contract green
+ routing/budget/health/fallback tests green
+ normalized stream/async lifecycle green
+ caller provider-SDK/key bypass scan green
+ hosted required gates green
```

Next node: **NODE-23 — Capability Registry**.

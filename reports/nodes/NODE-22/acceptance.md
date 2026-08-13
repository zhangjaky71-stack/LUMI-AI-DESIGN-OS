# NODE-22 Acceptance — Model Gateway

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Implementation scope

- [x] Provider-neutral `ModelRequest` and normalized result/stream contracts.
- [x] Initial capability vocabulary for LLM/image/video/embedding/OCR.
- [x] ProviderAdapter / registry / health / budget / telemetry ports.
- [x] Capability/quality/latency/policy/region/health/budget router.
- [x] Explainable accepted/rejected routing reason codes.
- [x] Soft provider/model preferences that cannot bypass policy.
- [x] Provider-local retry separated from cross-provider fallback.
- [x] Fallback restricted to fallbackable + proven `NOT_ACCEPTED` errors.
- [x] Ambiguous accepted/unknown provider outcomes block retry/fallback.
- [x] Mandatory paid invocation guard for every ModelGateway instance.
- [x] Separate mandatory paid stream guard for streaming.
- [x] Request-local budget reservation boundary, replaceable by NODE-27.
- [x] Normalized usage, cost confidence, price snapshot, and telemetry.
- [x] Telemetry excludes raw prompts/reference assets.
- [x] Deterministic MockProvider for LLM/structured/image/video/embedding/OCR.
- [x] Mock normalized stream and async video lifecycle.
- [x] Real OpenAI Responses HTTP adapter for reasoning + structured output.
- [x] OpenAI adapter defaults to `store=false` and does not depend on SDK.
- [x] OpenAI wire contract tested through fake transport without a live key.
- [x] Provider credentials/imports statically forbidden in caller runtimes.
- [x] Provider-neutral API + client facade.

## Acceptance cases authored

- [x] capability routing;
- [x] soft preference scoring;
- [x] unhealthy provider filtering;
- [x] hard budget filtering;
- [x] safe 429 fallback;
- [x] unsafe unknown 5xx outcome blocks fallback;
- [x] provider retry obeys Retry-After;
- [x] concurrent duplicate paid request -> one provider invocation;
- [x] normalized stream chunks;
- [x] async video pending/completed lifecycle;
- [x] deterministic structured MockProvider output;
- [x] provider-neutral API/client boundary;
- [x] paid guard required at construction;
- [x] OpenAI `store=false` request contract;
- [x] OpenAI standard output/usage normalization;
- [x] OpenAI structured output payload;
- [x] OpenAI 429/5xx delivery-state classification;
- [x] OpenAI key absent from adapter repr;
- [x] provider-native caller message fields rejected.

## Evidence status

No hosted PASS is claimed yet. The repository's GitHub Actions jobs remain externally blocked by the already-confirmed account payment / Actions spending-limit condition.

NODE-22 remains **not COMPLETE** until the dedicated Model Gateway workflow receives a runner and the required gates execute green.

## Required green evidence

- [ ] frozen workspace install;
- [ ] static architecture/secret boundary;
- [ ] Ruff;
- [ ] Pyright;
- [ ] Model Gateway unit suite;
- [ ] MockProvider full integration;
- [ ] no inherited repository regression.

Next node after green acceptance: **NODE-23 — Capability Registry**.

# NODE-46 Acceptance — Image Generation

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

Hosted GitHub Actions PASS and live-provider visual-quality acceptance are not claimed.

## Delivered

- independent dependency-light `lumi_image_generation` runtime package;
- seven frozen creation modes with NODE-47 edit/mask boundary;
- explicit reference roles and mode-specific preflight requirements;
- provider-neutral structured prompt blocks;
- budget-aware variant selection without hard-requirement degradation;
- deterministic root/variant operation ids for NODE-20 paid idempotency;
- 202 submit/status/cancel public API with provider execution outside HTTP;
- sync and durable async-provider lifecycle contracts;
- poll uncertainty remains pending instead of becoming false failure;
- current rights/permission recheck before invoke and async finalization;
- Asset Resolver references require explicit approval evidence;
- NODE-22 Model Gateway adapter using current normalized contracts;
- NODE-27 remains the sole monetary settlement owner;
- provider output MIME/container/decode/dimension/checksum/alpha validation;
- fail-closed NODE-39/NODE-43/NODE-44 postflight seams;
- provider safety HARD rejection;
- NODE-42 immutable RASTER_IMAGE DRAFT/READY Artifact integration;
- conservative generated-output rights, never automatic commercial approval;
- full generation provenance snapshot including provider/model/revision/routing/pricing;
- split PostgreSQL codec/job-write/repository adapters for reviewable transaction boundaries;
- forward migration `20260817_0015` on `20260817_0014`;
- deterministic 7-case control-plane eval, runtime smoke, static validator and five-gap ledger.

## Local evidence

Observed against the isolated final candidate before GitHub publication:

```text
8 passed in 0.06s
NODE46_API_SCHEMA_DOMAIN_PASS
NODE46_SPEC_CODEC_PASS
NODE46_IMAGE_GENERATION_EVAL_PASS cases=7
visual_quality_claimed=false
NODE46_IMAGE_GENERATION_RUNTIME_SMOKE_PASS
queued=202-style selected_variants=2 provider_invocations=2 artifacts=2
NODE46_IMAGE_GENERATION_VALIDATION_PASS
generation_modes=7
required_endpoints=3
fixture_cases=7
production_gaps=5
NODE46_PYTHON_COMPILEALL_PASS
NODE46_AST_PARSE_PASS files=34
NODE46_LINE_WIDTH_PASS files=34
```

The isolated environment does not contain the complete repository workspace, so the two current
stack integration tests for NODE-22 Model Gateway and NODE-42 Artifact Engine are authored for the
dedicated hosted workflow but are not claimed as locally executed. No repository-pinned Python
3.12/uv, Ruff or Pyright PASS is claimed locally.

## Hosted acceptance evidence

Implementation head `d2f1dbcd36a6be3a253e30300f25318b985c5525` is published on PR #113.
The connected GitHub App can read PR metadata and repository contents and can write the branch,
but its Actions/checks read endpoints currently return:

```text
403 Resource not accessible by integration
```

for both commit workflow-run inspection and commit check-run inspection. The combined-status API
returns no visible statuses. Therefore this acceptance record does **not** claim that the dedicated
NODE-46 workflow received a runner, executed any step, passed, or failed. The hosted acceptance
evidence itself is externally unavailable to the current integration and is classified
`BLOCKED_EXTERNAL`; this is not evidence of an Image Generation code, migration, provider, test,
Ruff or Pyright failure.

Before NODE-46 can be COMPLETE, the dedicated hosted workflow must be inspectable and must execute
the frozen workspace install, NODE-46 runtime/current-stack adapter tests, deterministic eval,
smoke, static validator, migration/runtime compile, gap parse, Ruff and Pyright.

## Safety and correctness boundaries

- NODE-46 has no `IMAGE_EDIT` or `IMAGE_MASK_EDIT` route; those are NODE-47.
- Provider-native payloads remain in NODE-22 provider adapters.
- No prompt/semantic creative cache reuses output across distinct operation ids.
- Reference authorization occurs before paid invoke and is refreshed during worker/async flow.
- Provider URLs are never Artifact storage truth.
- A corrupt/rejected paid result can retain cost evidence without creating a READY Artifact.
- Required HARD postflight service unavailability is a rejection.
- Generated output is `UNREVIEWED`; model generation is not a commercial-rights assertion.
- `image_generation_cost_projection` is non-monetary audit evidence; NODE-27 settlement is truth.

## Live-provider quality gate

The deterministic eval proves control-plane behavior, not image aesthetics or semantic quality.
Before COMPLETE, selected production provider/model revisions need approved NODE-23 benchmark
snapshots covering at minimum Chinese poster text fidelity, product/logo consistency, brand style,
multiple aspect ratios, transparent assets, provider latency/cost and fallback behavior.

## Database qualification

Migration `20260817_0015` adds tenant-scoped generation specs, jobs, candidates, async pending state
and cost projection. Root operation and per-variant operation uniqueness support idempotency.
Composite relationships and a candidate tenant trigger prevent cross-organization job attachment.
The cost table constrains monetary ownership to `NODE27_MODEL_GATEWAY_SETTLEMENT`.

No live PostgreSQL migration/concurrency/load run is claimed locally.

## Production gaps

Exactly five are tracked in `gap-ledger.json`.

Next node: **NODE-47 — Image Edit**.

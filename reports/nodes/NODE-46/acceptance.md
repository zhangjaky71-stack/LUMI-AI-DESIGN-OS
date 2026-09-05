# NODE-46 Acceptance — Image Generation Pipeline

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## Engineering evidence

| Requirement | Evidence | Status |
|---|---|---|
| Structured provider-neutral generation spec | `model.py` | Implemented |
| Seven frozen generation modes | `GenerationMode`, fixture, validator | Implemented |
| NODE-47 edit boundary preserved | `model_gateway_adapter.py`, static validator | Implemented |
| Explicit reference roles | `ImageReference` | Implemented |
| Scope-first reference authorization | `asset_intelligence_adapter.py` | Implemented |
| Commercial rights filtering | NODE-45 adapter + tests | Implemented |
| Model Gateway routing/invoke adapter | `model_gateway_adapter.py` | Implemented |
| Budget-aware variant count | `variants.py` + tests | Implemented |
| Root operation idempotency | `repository.py`, `pipeline.py` | Implemented |
| Per-variant paid operation identity | UUIDv5 variant operations | Implemented |
| No prompt/semantic creative-content cache | operation-only reuse + test/static gate | Implemented |
| Async provider persisted state | `PendingInvocationRecord`, repository | Implemented |
| Async Worker recovery | `resume_pending()` + tests | Implemented |
| Provider poll uncertainty remains pending | hardened pipeline | Implemented |
| Output MIME/decode/dimension/checksum gate | `image_validation.py` | Implemented |
| Transparency validation | PNG alpha gate + tests | Implemented |
| Provider URL not durable truth | durable generated S3 namespace + Artifact adapter | Implemented |
| Constraint / Brand / Identity postflight | `validation.py` | Implemented |
| Required validator unavailable fail-closed | `validation.py` + tests | Implemented |
| Provider safety hard rejection | `pipeline.py` + tests | Implemented |
| Complete constraint snapshot + provenance | hashing / Artifact adapter | Implemented |
| Failed/corrupt paid result keeps cost truth | cost-before-output-validation contract | Implemented |
| Canonical Hosted persistence | canonical `generations` + Artifact/outbox tables | Implemented source; PostgreSQL execution pending |
| Legacy parallel `image_generation_*` tables excluded | integration SQL assertion + legacy SQL warning | Implemented contract; execution pending |
| Product API canonical producer | `ImageGenerationControlPlane` | Implemented |
| Product API -> Task/spec -> outbox binding | `validate_image_generation_producer_contract.py` | Implemented source; Hosted execution blocked |
| Outbox -> canonical image Celery route | `MediaJobOutboxDispatcher` producer contract | Implemented source; Hosted execution blocked |
| `image.transform` -> Hosted Worker runtime | Worker app/runtime producer contract | Implemented source; Hosted execution blocked |
| API + Worker producer provenance | `production/runtime-images/manifest-v1.json` static producer contract | Implemented |
| Static architecture validator | `validate_image_generation.py` | Implemented; Hosted execution blocked |
| Dedicated five-stage CI | `.github/workflows/image-generation.yml` | Implemented; Hosted runner execution blocked |
| Worker Media image build/import/liveness smoke | `worker-media-image-smoke` | Implemented workflow; execution blocked |
| Live provider visual-quality benchmark | NODE-23 selected-provider evidence | **Pending** |

## Canonical product-to-Worker producer closure

The source-level producer path is now explicitly fail-closed across the whole chain:

```text
POST /generations
  -> GenerationRuntimeGateway
  -> ImageGenerationControlPlane
  -> canonical Generation + Task
  -> versioned image_generation_spec in Task.input_json
  -> canonical job.dispatch.requested outbox row
  -> MediaJobOutboxDispatcher
  -> lumi.jobs.image.transform / lumi.media.image
  -> Worker Media image_transform
  -> HostedImageGenerationRuntime
```

`scripts/validate_image_generation_producer_contract.py` now requires all of the following:

1. the production app installs `GenerationRuntimeGateway` and `/generations` calls `create_generation` with idempotency;
2. `ImageGenerationControlPlane` remains a DB-only producer with advisory-lock/idempotency protection and no direct Provider/Celery network side effect;
3. Task input contains only the canonical schema version, job kind, and encoded `image_generation_spec` before the Generation/outbox/idempotency operation is finalized;
4. dispatch revalidates organization/project/task/operation identity and semantic hash before staging the outbox payload;
5. `MediaJobOutboxDispatcher` maps `IMAGE_TRANSFORM_TASK_NAME` to the canonical queue/routing key, increments publish attempts before broker publication, and marks `published_at` only after successful publication;
6. Worker `image.transform` cannot regress to an accepted-only placeholder and must enter `HostedImageGenerationRuntime` through `TaskJobStore -> execute_job`;
7. API and Worker runtime-image provenance must contain the producer, dispatcher, and Hosted consumer sources;
8. both Image Generation and Final Acceptance workflows must execute and syntax-gate the producer contract.

The Image Generation workflow now path-filters the producer/dispatcher/provenance sources and runs this contract in the first `image-generation-contract` job, so NODE-46 can no longer rely only on a later Final Acceptance source check.

## Key safety / correctness assertions

1. Provider SDK payload construction does not belong to NODE-46 domain code.
2. Image edits and masks remain NODE-47 capabilities.
3. Reference assets are authorized by tenant/permission/rights scope before paid generation.
4. UNKNOWN rights are not silently promoted for commercial use.
5. Identical creative semantics under a new operation id are not auto-reused as cached output.
6. A repeated paid operation id with changed semantics fails closed.
7. Each selected variant has a stable paid operation id.
8. Budget reduction changes candidate count, not hard output/identity requirements.
9. Provider output refs are staging inputs; durable generated S3 object + checksum + ArtifactVersion are truth.
10. Required HARD validator outage is a rejection, not a pass.
11. Provider safety block is a HARD rejection.
12. Corrupt/rejected paid Provider results remain visible in canonical cost reconciliation.
13. Async poll uncertainty remains pending instead of lying about remote completion.
14. Product API generation creation and media broker publication are separated by a durable transactional outbox.
15. A producer change cannot bypass canonical Task/spec scope checks or route directly to a Provider.
16. Worker Media consumes only the canonical `image.transform` task envelope and private Model Gateway boundary.

## Workspace / lock discipline

`services/image-generation` is now a canonical root uv workspace member and Worker Media declares `lumi-image-generation` as a production dependency.

The current checked-in `uv.lock` is **stale**. Root workspace membership and the lock manifest differ by six packages:

```text
lumi-auth
lumi-domain
lumi-project-core
lumi-asset-storage
lumi-image-generation
lumi-video-generation
```

This is a system-wide frozen-install blocker, not a NODE-46-only cosmetic mismatch. The lock must not be hand-edited. The only accepted closure is the canonical resolver path:

```text
uv lock
-> python3 scripts/validate_uv_workspace_lock.py
-> uv lock --check
-> uv sync --all-packages --frozen
```

The current execution environment available in this session has no external DNS/package-resolution access, and the GitHub-hosted runner is failing before executable steps begin, so no resolver-generated `uv.lock` is claimed here.

## Required Hosted CI

The current Image Generation workflow requires five stages:

```text
image-generation-contract
image-generation-quality
worker-media-image-smoke
image-generation-integration
image-generation-benchmark
```

The first stage now includes both NODE-46 architecture validation and the canonical product-to-Worker producer binding contract. Quality uses the frozen all-workspace environment plus Ruff/Pyright; integration exercises PostgreSQL producer/repository behavior; smoke builds and starts the real Worker Media image; benchmark remains synthetic and cannot certify live Provider quality.

## Hosted runner evidence status

Latest sampled producer-closure head: `ee5ca15d2849d50c70c946de0f5aac9bca252f07`.

Image Generation run `32455525781`:

```text
image-generation-contract
  job_id: 96691955849
  conclusion: failure
  steps: null
  logs_url: null

image-generation-quality: skipped
worker-media-image-smoke: skipped
image-generation-integration: skipped
image-generation-benchmark: skipped
```

No checkout, Python compilation, producer validator, `uv`, Ruff, Pyright, pytest, PostgreSQL, Docker build, Worker startup, or benchmark command is evidenced as having run. Therefore this red workflow is neither an application/test failure nor PASS evidence; it remains consistent with the existing GitHub-hosted runner/account/scheduling blocker.

## Synthetic evidence honesty

Source contracts and MockProvider/domain tests can validate state-machine, idempotency, rights, routing, output validation, provenance, outbox, and Worker binding semantics. They do **not** demonstrate production image-model quality such as Chinese poster text fidelity, product/logo preservation, brand fidelity, transparent-background quality, live latency, or live pricing accuracy.

## Live provider benchmark gate

Production routing remains gated until the exact selected provider/model revisions have approved NODE-23 evidence for at least:

```text
chinese_poster_text_fidelity
product_consistency
brand_style
multiple_aspect_ratios
transparent_asset
cost_latency
fallback
```

No live-provider score is fabricated by NODE-46.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Blocking completion evidence:

1. canonical `uv.lock` must be resolver-regenerated and frozen all-workspace sync must pass;
2. Hosted Image Generation jobs must actually execute with step/log evidence and pass;
3. PostgreSQL producer/repository acceptance and Worker image build/import/liveness must execute successfully;
4. exact accepted runtime-image provenance/attestations must be captured from real promoted images;
5. selected production-routed image provider/model revisions need approved live benchmark snapshots;
6. NODE-71/72 staging and production evidence must close before NODE-73 can pass.

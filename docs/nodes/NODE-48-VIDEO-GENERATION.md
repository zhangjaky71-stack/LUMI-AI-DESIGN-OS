# NODE-48 — Video Generation & Composition

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P1 product parity, P0 architecture-ready  
> Depends on: NODE-19, NODE-22, NODE-23, NODE-27, NODE-42, NODE-43, NODE-44, NODE-46  
> Produces: Storyboard/Shot/Keyframe/Video Provider async jobs、typed media composition、Video Artifact lineage

---

## 1. Outcome

NODE-48 implements video generation as a durable external-wait workflow rather than blocking an Agent/LangGraph worker while a video provider renders.

Supported runtime modes:

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
STORYBOARD_MULTI_SHOT
```

The runtime owns shot orchestration and timeline composition. Provider SDKs, credentials and provider-native request schemas remain behind NODE-22 Model Gateway.

## 2. Implemented files

```text
services/video-generation/
  src/lumi_video_generation/
    model.py
    storyboard.py
    repository.py
    ports.py
    model_gateway_adapter.py
    pipeline.py
    validation.py
    artifact_adapter.py
    media_sandbox.py
    inmemory.py
  tests/test_video_generation.py

db/migrations/0007_video_generation.sql
fixtures/video-generation/node-48-conformance.json
scripts/validate_video_generation.py
scripts/benchmark_video_generation.py
docs/runtime/VIDEO-GENERATION-V1.md
reports/nodes/NODE-48/acceptance.md
reports/nodes/NODE-48/provider-benchmark.md
.github/workflows/video-generation.yml
```

Cross-node change:

```text
services/model-gateway/src/lumi_model_gateway/routing.py
```

adds request-scoped exact provider-key allow/exclude filtering while preserving existing behavior for requests that do not provide these constraints.

## 3. VideoTaskSpec

The executable task contract pins:

- organization/project/task/operation;
- mode;
- prompt and negative prompt;
- Decimal duration;
- aspect ratio;
- width/height/FPS;
- Decimal total task budget;
- source image asset/version/checksum;
- shots;
- optional audio tracks;
- Brand Rule Set version;
- Identity requirement versions;
- code Git SHA;
- optional-shot policy;
- quality retry limit.

`operation_id` is the idempotency boundary. A reused operation with changed semantic hash fails closed.

## 4. Storyboard and paid operations

Each shot contains:

```text
shot_id
duration
prompt
camera_motion
subject_action
source_ref?
continuity_refs[]
transition_to_next
optional
```

Storyboard compilation enforces unique IDs and exact total duration.

Each initial shot receives a stable paid operation ID. Every quality retry receives a different stable paid operation ID. Retry is therefore separately auditable and billable.

## 5. Long-running execution

Implemented state flow:

```text
start
 -> estimate
 -> submit one shot
 -> WAITING_EXTERNAL

resume event
 -> one poll only
 -> PENDING => return
 -> terminal => reconcile cost
 -> materialize/probe
 -> postflight
 -> Artifact
 -> next shot / compose
```

The pipeline contains no sleep loop.

Provider terminal results are archived by paid attempt so a worker crash after provider completion can replay the same terminal outcome without another model call.

## 6. Provider capability and feature routing

Top-level Model Gateway capability:

```text
video.text_to_video
video.image_to_video
```

Fine-grained NODE-23 feature facts:

```text
video.start_frame
video.reference_image
video.camera_controls
```

If a shot requires a fine-grained feature, a pinned `VideoFeatureRegistry` snapshot is mandatory. It resolves allowed exact `provider:model` keys; Model Gateway enforces the allowlist before paid execution.

Quality retries add the previous provider key to `excluded_provider_keys` and re-route.

## 7. Budget and fallback

Task budget is cumulative across shots and retries.

Allowed fallback:

- NODE-22 safe transport fallback;
- a new quality retry paid operation;
- alternate provider via exclusion;
- explicit optional-shot drop when policy allows;
- user action after exhausted hard-required attempts.

Forbidden fallback:

- silently weakening Identity;
- silently weakening Brand requirements;
- lowering required output dimensions/FPS;
- pretending a dropped required shot is success;
- reusing a paid operation for another provider attempt.

## 8. Continuity

Continuity references support:

```text
FIRST_FRAME
PREVIOUS_TAIL
EXPLICIT_REFERENCE
```

Sequential storyboards automatically feed the previous READY clip tail frame to the next shot unless another previous-tail policy is explicit.

Corresponding clip ArtifactVersion IDs are preserved as provenance/lineage inputs.

## 9. Postflight

Shot postflight includes:

- decode;
- MP4 MIME;
- resolution;
- FPS;
- duration;
- provider safety;
- NODE-44 Identity keyframe continuity;
- NODE-43 Brand keyframe continuity.

Required Identity/Brand validator outage is HARD unavailable/reject.

Final composition validates final duration against the actual READY timeline and validates final resolution.

## 10. Artifact model

Every materialized shot attempt creates its own VIDEO ArtifactVersion. Rejected first attempts remain auditable and are not overwritten by retries.

Lineage:

```text
source/reference version -> REFERENCE_USED -> shot attempt
shot clip versions       -> COMPOSED_FROM  -> final video
```

Only PASS clips are selected into the final timeline.

Final output includes the VIDEO Artifact plus optional thumbnail/subtitle files.

## 11. Typed media composition

`VideoTimeline` contains:

```text
clips[]
overlays[]
audio_tracks[]
transitions[]
output_spec
```

`FfmpegArgvCompiler` compiles this typed structure to argv only. User prompt/content is never concatenated into a shell command.

Input paths must be resolved under `/sandbox/` by a trusted resolver. Execution requires an injected `SandboxExecutor` with network-disabled/time/CPU/memory limits. There is no local subprocess fallback in the domain runtime.

Implemented V1 media operations:

- CUT concat;
- overlays;
- multi-track audio offset/gain/mix;
- fixed output duration;
- H.264/AAC MP4;
- fixed FPS/resolution;
- faststart.

CROSSFADE fails closed in V1 until deterministic transition math and tests are added.

## 12. Persistence

`0007_video_generation.sql` contains:

```text
video_generation_jobs
video_generation_shots
video_provider_jobs
video_generation_cost_reconciliation
video_timelines
video_generation_provenance
video_validation_findings
```

Key DB invariants:

- one root operation per organization;
- one current paid operation per shot;
- terminal provider attempts retained;
- only one active provider attempt per shot;
- Decimal/numeric cost fields;
- ArtifactVersion foreign keys for final/clip outputs;
- provider URL is never durable storage truth.

## 13. Tests and synthetic evidence

Executable tests cover:

- async submit/resume with one poll per resume;
- completed resume idempotency;
- multi-shot Artifact lineage;
- previous-tail continuity;
- Identity validator unavailable fail-closed;
- quality retry with new paid operation and provider exclusion;
- optional-shot PARTIAL completion;
- cumulative budget;
- cancellation;
- real NODE-22 MockProvider async submit/poll/poll;
- image-to-video feature-registry routing;
- typed FFmpeg argv/path safety;
- unsupported transition fail-closed.

`node-48-conformance.json` defines a 48-case synthetic contract matrix.

## 14. Benchmark honesty

`benchmark_video_generation.py` measures only dependency-free Storyboard/Timeline planning and hash work.

It excludes:

- provider queue/inference;
- media upload/download;
- FFmpeg encode;
- model-based Identity/Brand validators;
- PostgreSQL.

Production video quality is gated by `reports/nodes/NODE-48/provider-benchmark.md` and remains pending until live provider revisions are benchmarked.

## 15. Dedicated CI

Required hosted jobs:

```text
video-generation-contract
video-generation-quality
video-generation-integration
video-generation-benchmark
```

The integration job must apply Artifact + NODE-48 migrations to a fresh PostgreSQL instance and run Model Gateway / Artifact history regressions.

## 16. Acceptance status

Engineering implementation: **IMPLEMENTED**.

Completion remains blocked by:

1. hosted workflow jobs actually executing green;
2. approved live provider benchmark snapshots for production-routed video models.

A GitHub Actions account billing/spending-limit zero-step job is an external validation blocker, not PASS and not observed code failure.

Next node: **NODE-49 — Export & Rendering**.

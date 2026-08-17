# VIDEO-GENERATION-V1

## Scope

NODE-48 owns the provider-neutral long-running video generation control plane from a structured storyboard to verified shot clips and a composed final Video Artifact. It deliberately does not turn an Agent/LangGraph request into a long provider polling loop.

## Ownership boundaries

- **NODE-19 Queue/Event Runtime** owns durable scheduling, retries, DLQ and worker wakeups.
- **NODE-22 Model Gateway** owns provider/model routing, paid side-effect guard, fallback and provider transport.
- **NODE-27 Cost Ledger** remains the monetary source of truth. NODE-48 persists only shot-level audit projections.
- **NODE-42 Artifact Engine** owns immutable Artifact/ArtifactVersion lineage.
- **NODE-43 Brand Rules** and **NODE-44 Identity Engine** remain validation authorities.
- **NODE-48** owns storyboard compilation, shot lifecycle, provider-pending state, clip technical validation, video-specific provenance, typed timeline and render contracts.

## Runtime state machine

```text
PLANNED
  -> submit each shot once through NODE-22
  -> WAITING_EXTERNAL
  -> scheduler/webhook wakes NODE-48
  -> resume() performs at most one poll per waiting shot
       PENDING   -> WAITING_EXTERNAL
       FAILED    -> FAILED / explicit per-shot retry
       CANCELLED -> CANCELLED
       COMPLETED -> staging -> probe -> Identity/Brand -> READY
  -> all shots READY
  -> COMPOSING
  -> typed FFmpeg sandbox render
  -> final Artifact append
  -> COMPLETED
```

`resume()` is intentionally bounded. Provider wait time is externalized to workers/schedulers and must not occupy the Agent graph execution thread.

## Storyboard and shot idempotency

Every shot receives a stable UUIDv5 paid operation id derived from:

```text
root operation id + shot id + retry ordinal
```

The initial attempt is deterministic. Every explicit retry receives a distinct operation id so NODE-20/NODE-22 paid side-effect idempotency can distinguish a new accepted provider call from a replay.

Repository idempotency is scoped by `(organization_id, operation_id)` plus the task semantic hash. Reusing an operation id with a different semantic payload fails closed.

## Modes

The domain supports:

- `TEXT_TO_VIDEO`
- `IMAGE_TO_VIDEO`
- `KEYFRAME_TO_VIDEO`
- `PRODUCT_MOTION`
- `LOOP`

NODE-22 capabilities remain `video.text_to_video` and `video.image_to_video`. Higher-level modes compile onto those provider-neutral capabilities.

## Provider feature routing

Video-specific provider features are represented by a versioned `VideoFeatureRegistry` snapshot. Current hard features are:

- `video.start_frame`
- `video.reference_image`
- `video.camera_controls`

If a shot requires any of these and no feature registry is supplied, routing fails before a paid call. Providers known by the snapshot but missing the required feature are excluded through current NODE-22 routing hints. The registry snapshot id is retained in request metadata for auditability.

## Async provider contract

A production video submit must return:

```text
status = PENDING
provider_request_id != null
```

A synchronous terminal result is rejected with `VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED`. This creates a uniform long-running protocol even when a provider SDK offers mixed sync/async behavior.

Polling uses the persisted provider/model/request id and verifies that provider identity does not change during the async lifecycle. Cancellation calls NODE-22 when supported; otherwise the job remains `CANCEL_REQUESTED`. A late completion after cancellation is discarded rather than materialized into a user-visible artifact.

## Budget and cost

Before submission NODE-48 requests a route estimate for every shot. The sum must fit the task budget. The Model Gateway also receives a bounded per-shot request budget.

Actual provider settlement stays inside NODE-27 / Model Gateway. `video_generation_cost_projection` is audit-only and has a database constraint that fixes `monetary_owner` to `NODE27_MODEL_GATEWAY_SETTLEMENT`.

## Provider output boundary

Provider URLs/references are transient. `VerifiedVideoOutputAdapter` performs:

1. fetch to staging;
2. maximum-size enforcement;
3. MIME allowlist (`video/mp4`, `video/webm`);
4. media probe;
5. SHA-256 calculation;
6. durable internal storage write;
7. rejection of external/network durable references.

Provider output references must not become durable Artifact truth.

## Clip validation

Every completed shot is validated before it becomes READY:

- supported container;
- exact target dimensions;
- duration tolerance;
- at least one decodable frame;
- black-frame ratio threshold;
- provider safety hard-rejection metadata;
- Identity Engine when identity refs are present;
- Brand Rules when a brand snapshot is present.

Identity/Brand dependencies fail closed: if a required validator is unavailable, the clip is rejected.

## Partial retry

A failed shot may be retried independently without regenerating already READY shots. The retry receives a new paid operation id and retry ordinal. Production routing should exclude the failed provider when provider/model failure or validation evidence indicates a provider-specific issue; the interface already accepts provider exclusions.

## Timeline and media sandbox

NODE-48 exposes a renderer-neutral `VideoTimeline`. P0 supports ordered video clips with `CUT` and bounded `FADE`, plus reserved audio/subtitle references.

`FfmpegArgvCompiler` only emits a typed argv tuple. It never emits a shell string and never accepts arbitrary user filter text. Network/protocol inputs, relative paths, NUL/newline paths and traversal are rejected. Execution is delegated to a mandatory sandbox with explicit time, memory, CPU and output-size limits.

## Artifact and provenance

Shot clips and the final video are appended through a NODE-42 port; Artifact Engine remains the lineage authority. Final video provenance contains:

- task semantic hash;
- each shot id and paid operation id;
- retry ordinal;
- provider/model/request id;
- source Asset ids and rights snapshots;
- identity refs;
- shot cost projection;
- renderer version;
- brand snapshot;
- AgentRun / agent / recipe / skills / git commit.

No prompt secrets, provider credentials, signed URLs or raw provider payloads belong in durable provenance.

## Persistence

Alembic `20260817_0017` adds:

- `video_generation_specs`
- `video_generation_jobs`
- `video_generation_shots`
- `video_provider_jobs`
- `video_generation_clips`
- `video_generation_cost_projection`
- `video_webhook_dedupe`

The migration is directly chained to NODE-47 revision `20260817_0016`.

## Validation gates

The dedicated workflow requires:

1. compile + static architecture validator + gap ledger parse;
2. deterministic lifecycle/security tests + Ruff + Pyright;
3. real PostgreSQL migration to Alembic head and NODE-48 table verification;
4. deterministic 2,000-shot planning benchmark.

These control-plane gates do **not** certify real visual quality. Production completion additionally requires approved live provider/model evidence for motion quality, product/identity/brand continuity, start-frame adherence, cancellation semantics, latency and cost.

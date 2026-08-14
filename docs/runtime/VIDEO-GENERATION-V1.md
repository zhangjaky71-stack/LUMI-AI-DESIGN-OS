# Video Generation Runtime V1

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

NODE-48 owns the long-running video-generation and final timeline-composition workflow. It consumes provider execution from NODE-22, provider capability/benchmark facts from NODE-23, cost semantics from NODE-27, Artifact history from NODE-42, Brand rules from NODE-43 and Identity evidence from NODE-44.

## 1. Ownership boundary

NODE-48 owns:

- `VideoTaskSpec`;
- deterministic Storyboard compilation;
- per-shot paid operation identity;
- long-running submit / external-wait / resume state;
- per-shot budget and cost reconciliation;
- start-frame / previous-tail / explicit-reference continuity;
- keyframe postflight orchestration;
- shot Artifact creation;
- typed `VideoTimeline`;
- typed media-sandbox render request;
- final VIDEO Artifact and `COMPOSED_FROM` lineage.

NODE-48 does **not** own:

- provider SDK credentials or native provider payloads — NODE-22;
- provider/model benchmark truth — NODE-23;
- budget ledger authority — NODE-27;
- Artifact history semantics — NODE-42;
- Brand scoring — NODE-43;
- Product/Character/Logo identity scoring — NODE-44;
- final general-purpose export system — NODE-49.

## 2. VideoTask contract

`VideoTaskSpec` pins:

- organization / project / task / operation;
- generation mode;
- prompt + optional negative prompt;
- duration;
- aspect ratio;
- width / height;
- FPS;
- Decimal task budget;
- source image versions/checksums;
- storyboard shots;
- audio tracks;
- Brand Rule Set version;
- Identity requirements;
- code Git SHA;
- optional-shot policy;
- quality-retry limit.

The semantic hash excludes no material generation input. Reusing an operation ID with changed semantics fails closed.

## 3. Modes

V1 supports:

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
STORYBOARD_MULTI_SHOT
```

A single-shot task without an explicit storyboard is compiled into `shot-001`.

## 4. Storyboard

Each `ShotSpec` contains:

- `shot_id`;
- exact Decimal duration;
- shot prompt;
- camera motion;
- subject action;
- optional source image;
- continuity references;
- transition to next;
- explicit optional flag.

The sum of shot durations must equal task duration. Duplicate shot IDs fail before any provider call.

Each shot receives a stable UUIDv5 paid operation. A quality retry receives a different stable UUIDv5 paid operation, so the retry is a separate billable action rather than a mutation of the original call.

## 5. Long-running state machine

Video generation is an external-wait workflow.

```text
start
  -> submit one shot
  -> WAITING_EXTERNAL

resume
  -> poll at most once
  -> still pending: return immediately
  -> terminal: reconcile cost + validate + persist
  -> submit next shot if needed
```

The pipeline contains no sleep/poll loop. LangGraph or queue workers do not remain occupied while a provider renders video.

Supported job states:

```text
SUBMITTING
WAITING_EXTERNAL
VALIDATING
COMPOSING
COMPLETED
PARTIAL
FAILED
CANCELLED
```

## 6. Provider-job crash recovery

Provider jobs are persisted by:

```text
organization_id
video_job_id
shot_id
paid_operation_id
provider/model
provider_request_id
request_hash
terminal result snapshot
```

Terminal provider-job rows are archived, not deleted. If a worker crashes after provider completion but before cost/Artifact completion, the next resume can replay the same terminal result without another provider call.

Cost reconciliation is idempotent by `paid_operation_id`.

## 7. Provider routing

The adapter maps to NODE-22 capabilities:

```text
video.text_to_video
video.image_to_video
```

V1 uses NODE-22 async status and cancellation APIs.

### 7.1 Provider feature registry

Some capabilities are finer-grained than the top-level model capability:

```text
video.start_frame
video.reference_image
video.camera_controls
```

NODE-48 therefore consumes a pinned `VideoFeatureRegistry` snapshot derived from NODE-23. When a shot needs one of these features, absence of the registry fails closed.

The feature registry resolves an allowlist of exact `provider:model` keys. NODE-22 applies the allowlist before paid invocation.

### 7.2 Quality retry exclusion

After a terminal provider or postflight quality failure, an allowed quality retry:

1. records the first attempt cost;
2. preserves its Artifact/provenance where an output exists;
3. creates a new paid operation ID;
4. adds the previous `provider:model` to request-level exclusions;
5. re-estimates total task budget;
6. submits to another eligible provider.

Hard Brand/Identity/output requirements are unchanged.

## 8. Continuity

Continuity inputs may be:

```text
FIRST_FRAME
PREVIOUS_TAIL
EXPLICIT_REFERENCE
```

For sequential storyboards, the previous READY shot tail frame is automatically added when a shot does not specify another previous-tail relation.

The previous clip ArtifactVersion is also recorded as lineage/provenance input.

A downstream shot cannot consume a PREVIOUS_TAIL dependency that is not READY.

## 9. Output materialization and probe

Provider URLs are transient/restricted inputs only. Durable truth is:

```text
storage_key
checksum_sha256
mime_type
width
height
duration_ms
durable_asset_ref
poster_frame_ref
tail_frame_ref
keyframe_refs
```

A video probe must establish:

- decodability;
- MP4 MIME/container contract;
- codec metadata;
- dimensions;
- FPS;
- duration;
- keyframe references;
- poster/tail frame references.

## 10. Postflight

Per-shot V1 checks include:

- decode integrity;
- MIME;
- resolution;
- FPS;
- duration;
- provider safety block;
- NODE-44 Identity continuity on sampled keyframes;
- NODE-43 Brand continuity on sampled keyframes.

When Identity requirements exist but the delegate is unavailable, validation returns HARD unavailable/reject. The same rule applies to a requested Brand Rule Set.

No validator outage is treated as PASS.

## 11. Artifact lineage

Every generated attempt with a materialized clip receives its own VIDEO ArtifactVersion. Attempt identity includes the paid operation ID, so rejected first attempts and successful retries coexist.

Shot lineage may contain `REFERENCE_USED` edges from:

- source ArtifactVersion;
- previous shot clip ArtifactVersion;
- explicit continuity parent versions.

Only PASS clips are selected for the final timeline.

Final VIDEO Artifact lineage:

```text
clip v1 --COMPOSED_FROM--> final video
clip v2 --COMPOSED_FROM--> final video
...
```

Thumbnail/poster/subtitle outputs are Artifact files/sub-artifacts rather than untracked provider URLs.

## 12. Optional shots

A shot may be dropped only when both are true:

```text
shot.optional == true
allow_optional_shot_drop == true
```

Explicit optional drop may occur because of budget or terminal/quality failure. The final job becomes `PARTIAL`, not `COMPLETED`.

Required Identity/Product constraints are never weakened to avoid a drop/failure.

## 13. Cost

All costs use Decimal in Python and `numeric(20,8)` in PostgreSQL.

Task budget is cumulative across initial attempts and retries. Every terminal accepted provider call is reconciled even when:

- the output is corrupt;
- postflight rejects it;
- a later provider retry succeeds.

## 14. Typed media sandbox

`VideoTimeline` is the only input to final composition.

It contains:

```text
clips[]
overlays[]
audio_tracks[]
transitions[]
output_spec
```

`FfmpegArgvCompiler` emits an argv tuple, never a shell command string. Input paths come only from `SandboxPathResolver` and must resolve under `/sandbox/`.

`SandboxLimits` requires network-disabled execution plus CPU/memory/time ceilings. Production execution requires an injected `SandboxExecutor`; there is no local subprocess fallback in the domain runtime.

V1 composition supports:

- CUT clip concatenation;
- pre-rendered overlays;
- multiple audio tracks;
- typed audio gain;
- typed audio offset;
- `amix`;
- H.264/AAC MP4;
- fixed FPS/resolution/duration;
- fast-start metadata.

CROSSFADE is declared in the timeline contract but intentionally fails closed in the V1 FFmpeg compiler until its deterministic transition math is implemented and tested.

## 15. Persistence

`0007_video_generation.sql` persists:

```text
video_generation_jobs
video_generation_shots
video_provider_jobs
video_generation_cost_reconciliation
video_timelines
video_generation_provenance
video_validation_findings
```

Provider attempts are append-preserved. A partial unique index permits only one active provider attempt per shot while retaining prior terminal attempts.

## 16. Events

Current lifecycle events include:

```text
video_generation.started
video_generation.external_wait
video_generation.shot_quality_retry
video_generation.shot_ready
video_generation.completed
video_generation.cancelled
```

Events carry identifiers and status/provenance references, not provider credentials or raw media bytes.

## 17. Synthetic vs live evidence

`fixtures/video-generation/node-48-conformance.json` defines 48 synthetic orchestration/contract cases.

`MockProvider` proves the NODE-22 submit/poll/cancel integration, but does not prove visual quality.

Production routing remains gated by `reports/nodes/NODE-48/provider-benchmark.md` until selected live provider revisions are benchmarked for prompt adherence, first-frame fidelity, Product/Character/Logo continuity, multi-shot temporal continuity, camera control, technical output, latency, cost, cancellation and fallback.

## 18. Completion rule

NODE-48 remains **IMPLEMENTED / VALIDATING / not COMPLETE** until:

1. hosted contract/quality/integration/benchmark jobs actually execute green; and
2. approved live provider benchmark snapshots exist for production-routed video models.

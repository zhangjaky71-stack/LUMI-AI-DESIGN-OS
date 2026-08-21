# NODE-48 — Video Generation & Composition

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P1 product parity, P0 architecture-ready  
> Depends on: NODE-19, NODE-20, NODE-22, NODE-23, NODE-27, NODE-42, NODE-43, NODE-44, NODE-46  
> Produces: durable Video generation jobs, async provider waits, typed media composition, canonical Video Artifact lineage

---

## 1. Outcome

NODE-48 implements provider-neutral video generation as a durable external-wait state machine rather than blocking an Agent/LangGraph worker while a provider renders.

The domain model can represent `TEXT_TO_VIDEO`, `IMAGE_TO_VIDEO`, and `STORYBOARD_MULTI_SHOT`, but the current Hosted production composition deliberately exposes only single-shot `TEXT_TO_VIDEO`. Unsupported reference/continuity/Identity/Brand/audio/provider-control features fail closed until their production boundary is implemented.

## 2. Production execution chain

Canonical Hosted execution is:

```text
API video.generate
  -> VideoGenerationControlPlane
  -> Task(type=video.render) + Generation + NODE-20 idempotency
  -> job.dispatch.requested outbox
  -> lumi.jobs.video.render / lumi.media.video
  -> TaskJobStore
  -> HostedVideoGenerationRuntime
  -> VideoGenerationPipeline
  -> private Model Gateway
  -> provider async job
  -> WAITING_EXTERNAL / wake
  -> private provider-output S3
  -> network-disabled Sandbox probe
  -> canonical shot Artifact
  -> typed FFmpeg composition
  -> durable final MP4 re-probe
  -> canonical final Artifact
```

Worker Media holds no provider credential.

## 3. Hosted V1 accepted contract

Current Hosted V1 requires:

- `TEXT_TO_VIDEO`;
- at most one required shot;
- exact 4, 8, or 12 second duration;
- CUT transition;
- no source image/reference/continuity input;
- no separate audio track;
- no Identity requirements;
- no Brand Rule Set requirement;
- no seed;
- no negative prompt;
- no camera-motion or subject-action provider control.

This is narrower than the domain schema by design. A field being representable in `VideoTaskSpec` does not mean Hosted production supports it.

## 4. Product producer and idempotency

`VideoGenerationControlPlane` owns the public producer boundary.

It atomically creates/binds:

- canonical `video.render` Task;
- canonical generic `Generation(capability=video.generate)`;
- NODE-20 API idempotency operation;
- dispatch outbox record.

Image and Video generation share the same API operation/idempotency namespace and advisory-lock pattern. Reusing an operation ID with changed semantics fails closed.

## 5. Long-running provider execution

Provider work is asynchronous:

```text
start
 -> estimate
 -> submit
 -> persist provider request identity
 -> WAITING_EXTERNAL

resume
 -> poll once
 -> pending => persist + ExternalWait
 -> terminal => reconcile cost + validate + continue
```

No worker sleep loop exists. External wake reuses the canonical dispatch identity and does not consume a task retry attempt.

Provider terminal snapshots are retained so a crash after provider completion does not require another paid provider call.

## 6. Provider boundary

Hosted Worker calls the private signed Model Gateway only.

The current OpenAI video adapter:

- exposes async text-to-video;
- validates duration before invocation;
- validates requested size against a pinned price card before invocation;
- sends only provider-supported native create fields;
- stages completed MP4 content to private provider-output S3;
- does not treat delete as proven cancellation;
- rejects unsupported deterministic/provider controls before paid work.

The Worker receives provider-neutral results and opaque private S3 refs rather than public media URLs.

## 7. Raw provider-output validation

Provider output is first checked for:

- private bucket/prefix identity;
- bounded size;
- MP4 MIME;
- checksum;
- network-disabled `ffprobe` decode/container evidence;
- durable server-side promotion identity.

Hosted raw-shot postflight then requires:

- decode integrity;
- MP4 MIME;
- requested resolution;
- requested duration within tolerance;
- provider safety not blocked.

### FPS ownership

`VideoTaskSpec.fps` is the final output contract.

The current Hosted provider create boundary does not own/configure FPS, so a raw provider clip is not rejected solely because its observed FPS differs from `spec.fps`. Raw FPS remains observable probe metadata.

Final FPS normalization is owned by typed FFmpeg composition and is verified again from the final durable MP4. This prevents a non-controllable provider property from causing an avoidable post-payment quality retry while preserving strict final-output correctness.

## 8. Typed media composition

`VideoTimeline` contains typed clips/overlays/audio/transitions/output spec. `FfmpegArgvCompiler` emits argv only and never interpolates user prompt text into a shell command.

Hosted media execution uses the remote Sandbox Runtime and a network-disabled child.

Current final composition guarantees:

- CUT concatenation;
- H.264 MP4;
- requested output width/height;
- requested output FPS;
- bounded requested duration;
- faststart metadata.

CROSSFADE remains fail-closed in V1.

## 9. Final durable media verification

The intermediate Sandbox bridge previously carried timeline-expected metadata. Hosted production no longer trusts those values as final evidence.

`HostedVerifiedVideoMediaSandbox` re-probes the already promoted final durable MP4 and requires actual-file evidence for:

- checksum/size identity;
- MP4 container/MIME;
- H.264 codec;
- requested width/height;
- requested FPS;
- requested duration;
- expected audio presence/absence.

Only probe-derived metadata is passed into final validation/Artifact creation.

## 10. Canonical persistence

Hosted production uses Alembic `0023_video_generation_runtime` for exactly:

```text
video_generation_jobs
video_provider_jobs
```

These are recovery/provider-attempt snapshots. `lumi_app` has SELECT/INSERT/UPDATE but not DELETE.

All other durable truth stays canonical:

- Task execution/external wait — TaskJobStore / `tasks`;
- public generation state — generic `generations`;
- paid side-effect identity — NODE-20;
- provider cost truth — NODE-27 `cost_ledger`;
- Video files/lineage/provenance — canonical Artifact tables;
- events/dispatch — `outbox_events`.

The historical seven-table `0007_video_generation.sql` design is not the Hosted production schema and must not be reintroduced as a parallel source of truth.

## 11. Cost

Every accepted paid provider attempt is reconciled against the canonical NODE-27 actual-cost row using tenant + paid-operation scope.

Worker Media does not insert/update/delete provider cost truth. Quality rejection or later retry does not erase the first attempt's cost.

## 12. Artifact lineage

Each materialized shot attempt gets its own canonical VIDEO ArtifactVersion. Rejected attempts remain auditable.

Final lineage uses:

```text
shot clip version --COMPOSED_FROM--> final video version
```

Final Artifact files reference only durable generated objects.

## 13. Public Generation sync

For API-created operations, the Worker repository synchronizes the generic public `generations` row in the same PostgreSQL transaction as its video recovery snapshot.

Public result JSON is sanitized. It exposes video/shot status, cost and Artifact IDs, but not provider request IDs.

Internal Agent/TaskGraph video jobs without a public Generation row safely continue without creating a duplicate product record.

## 14. Provider/job durability and privileges

Hosted recovery tables preserve provider identity and archive attempts by state rather than physical deletion.

PostgreSQL acceptance checks:

- recovery roundtrip;
- external-wait/wake persistence;
- canonical cost reconciliation;
- Artifact `COMPOSED_FROM` lineage;
- outbox idempotency;
- public Generation sync;
- no DELETE runtime privilege on video recovery tables;
- immutable cost/Artifact truth remains non-mutable.

## 15. Runtime image provenance

The canonical Worker Media image provenance must include the Hosted Video domain and Worker execution chain, including:

- video generation domain;
- private Model Gateway adapter;
- codec/repository/ports/artifacts/runtime;
- Sandbox bridge;
- final durable probe runtime;
- Hosted raw-validation runtime;
- scoped cost observer;
- job dispatch/external-wait runtime;
- Worker Dockerfile/entrypoint.

NODE-71 Staging Acceptance drills removal of every required Worker media source and blocks incomplete provenance.

## 16. Dedicated CI

The Video Generation workflow requires:

```text
video-generation-contract
video-generation-quality
worker-media-video-smoke
video-generation-integration
video-generation-benchmark
```

Quality includes all Hosted Worker `test_video_*.py` tests plus Ruff/Pyright. Integration includes API producer/outbox and Worker PostgreSQL recovery/privilege/public-generation acceptance.

The Worker image smoke must build the real Dockerfile and import/start the packaged production runtime.

## 17. Benchmark honesty

Synthetic storyboard/timeline benchmarks do not certify provider visual quality.

Live production routing remains gated on approved provider/model benchmark evidence for the configured `LUMI_VIDEO_MODEL_PROFILE`.

## 18. Acceptance status

Engineering implementation: **IMPLEMENTED / VALIDATING**.

Completion remains blocked by:

1. canonical `uv.lock` regeneration including `lumi-video-generation` and successful frozen all-workspace sync;
2. Hosted GitHub jobs actually executing with step/log evidence;
3. PostgreSQL/Docker/runtime-image evidence from a trusted runnable environment;
4. approved live provider/model benchmark snapshots;
5. NODE-71/72 staging and production evidence closure.

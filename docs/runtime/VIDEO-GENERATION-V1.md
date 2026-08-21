# Video Generation Runtime V1

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

NODE-48 owns the provider-neutral video-generation state machine and typed final media composition. The current Hosted production composition is deliberately narrower than the domain model and fails closed on controls that do not yet have an end-to-end provider/authorization boundary.

## 1. Ownership boundary

NODE-48 owns:

- `VideoTaskSpec` and semantic identity;
- deterministic storyboard compilation;
- per-shot paid-operation identity;
- long-running submit / external-wait / resume state;
- cumulative budget and cost reconciliation;
- provider-output materialization and technical postflight;
- shot Artifact creation;
- typed `VideoTimeline` composition;
- final VIDEO Artifact and `COMPOSED_FROM` lineage.

NODE-48 does **not** own:

- provider credentials/native payloads — Model Gateway;
- provider/model benchmark truth — NODE-23;
- canonical provider-cost ledger truth — NODE-27;
- Artifact history semantics — NODE-42;
- Brand/Identity scoring — NODE-43/NODE-44;
- general-purpose export — NODE-49.

## 2. Domain contract vs Hosted V1

The provider-neutral domain model can represent:

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
STORYBOARD_MULTI_SHOT
```

The current Hosted production composition intentionally accepts only:

```text
TEXT_TO_VIDEO
single required shot
4 / 8 / 12 seconds
CUT transition
no source/reference image
no separate audio track
no Identity requirement
no Brand Rule Set requirement
no deterministic seed
no negative prompt / camera motion / subject-action provider controls
```

Unsupported controls fail before a provider side effect. They are not silently weakened or ignored.

## 3. Canonical product producer

Public `video.generate` is produced by the API control plane, not directly by Worker Media.

The producer atomically creates/binds:

- canonical `Task` with type `video.render`;
- canonical generic `Generation` with capability `video.generate`;
- NODE-20 API idempotency operation;
- `job.dispatch.requested` outbox event routed to `lumi.jobs.video.render` / `lumi.media.video`.

Worker Media does not create a second product-generation API model.

## 4. Long-running execution

Hosted Video is an external-wait workflow:

```text
start
  -> estimate
  -> submit one provider job
  -> persist provider identity
  -> WAITING_EXTERNAL

wake/resume
  -> poll at most once
  -> pending: persist + return ExternalWait
  -> terminal: reconcile canonical cost + materialize + validate
  -> compose final output
```

There is no worker sleep/poll loop. External wake does not consume a task retry attempt.

## 5. Durable recovery state

Hosted production uses Alembic `0023_video_generation_runtime` for exactly two NODE-48 recovery tables:

```text
video_generation_jobs
video_provider_jobs
```

These tables preserve:

- canonical spec/job snapshots;
- provider/model/request identity;
- paid operation identity;
- request hash;
- terminal provider result snapshot.

Runtime privileges are SELECT/INSERT/UPDATE only; DELETE is not granted. Provider attempts are archived by state rather than physically erased.

The historical seven-table `0007_video_generation.sql` model is **not** the canonical Hosted production schema.

## 6. Canonical cross-node persistence

Other truth remains in existing canonical subsystems:

- `tasks` / TaskJobStore for execution lifecycle and external wait;
- `generations` for public Generation state/result;
- NODE-20 idempotency operations for paid side-effect identity;
- NODE-27 `cost_ledger` for provider cost truth;
- canonical Artifact/Branch/Version/File/Provenance tables for media lineage;
- `outbox_events` for durable domain/dispatch events.

Worker Video adapters are not allowed to create a parallel cost or Artifact ledger.

## 7. Provider boundary

Worker Media calls only the private signed Model Gateway. It does not hold provider credentials.

For the current OpenAI Hosted adapter:

- provider work is asynchronous;
- duration is restricted to 4/8/12 seconds;
- size must be enabled by the pinned video price card before invocation;
- provider output is staged as a private S3 `provider-output/v1/async/...` reference;
- source-image/reference inputs remain fail-closed until an authorized Asset-to-provider input boundary exists;
- cancellation remains fail-closed because deletion is not treated as proven in-progress cancellation.

### Provider-reconciled cancellation

Cancellation is provider-reconciled. `tasks.cancellation_requested_at` records user intent; it is **not** evidence that an already accepted asynchronous provider job stopped.

`video.render` therefore uses the Video-specific `execute_video_job` boundary rather than the generic request-equals-cancelled executor. When a cancellation request exists and NODE-48 already has a recovery row, Hosted execution performs this bounded sequence:

```text
attempt provider cancellation
  -> cancellation proven: persist CANCELLED
  -> cancellation unproven / still WAITING_EXTERNAL:
       poll the same provider request exactly once
         -> still pending: persist WAITING_EXTERNAL + cancellation_pending
         -> completed/partial: preserve real provider completion
         -> failed: preserve real provider failure
```

The cancellation reconciliation path never calls `pipeline.start()` and never submits replacement paid provider work. It explicitly disables quality retry while reconciling the existing Provider request, so Provider failure, postprocess failure, or validation failure after cancellation intent cannot launch another paid generation attempt. The cancel attempt and, when required, the single poll are reconciled in one Worker invocation and then flushed once through the canonical recovery/public-Generation/event UoW.

For the current OpenAI Videos adapter, deletion is deliberately **not** treated as cancellation proof. The adapter fails closed instead of issuing a DELETE and declaring success. This means a cancellation request can remain `WAITING_EXTERNAL` until the same provider request reaches a real terminal state.

Terminal provider truth wins races with cancellation intent: `COMPLETED`/`PARTIAL` remains succeeded, `FAILED` remains failed, and only a NODE-48 state actually confirmed as `CANCELLED` permits the Task to become cancelled. A job with no NODE-48 recovery row has no accepted provider identity and may be cancelled locally before provider work exists.

## 8. Provider output materialization and crash-safe cleanup

Provider output is never accepted through a public URL as durable truth.

The Worker:

1. validates the private provider-output S3 ref;
2. verifies size/MIME/checksum;
3. server-side copies it into the Sandbox exchange bucket;
4. runs network-disabled `ffprobe`;
5. validates decodability/container metadata;
6. server-side promotes the exact object into `generated/video/v1/...`;
7. verifies promotion size/checksum/MIME before creating a clip record.

The Worker does not download provider video bytes into the Worker process.

Hosted production wraps the output store with `DeferredProviderOutputStore`. The base adapter may request deletion from its `finally` block, but canonical `provider-output/v1/async/...` deletion is deferred until the recovery/public-Generation/event transaction has committed and the persisted snapshot matches the in-memory job. Sandbox-exchange probe files are still deleted immediately.

If the post-commit provider-output delete fails, the committed job is not failed or replayed. The object remains eligible for a narrowly scoped one-day S3 lifecycle rule on `provider-output/v1/async/`. Durable `generated/video/v1/...` objects are outside that lifecycle prefix.

This boundary prevents a crash after media/artifact materialization but before recovery persistence from deleting the only provider source needed for deterministic resume.

## 9. Raw-shot validation and FPS ownership

`VideoTaskSpec.fps` is the **final output FPS contract**.

The current Hosted provider create boundary does not expose an FPS control. Therefore raw provider clips are **not** rejected merely because observed provider FPS differs from `spec.fps`.

Hosted raw-shot validation remains fail-closed for:

- decode integrity;
- MP4 MIME;
- requested resolution;
- requested duration within tolerance;
- provider safety block.

Raw FPS is still probed and observable metadata, but final FPS ownership belongs to typed FFmpeg composition and the final durable probe.

The provider-neutral domain validator may retain stricter raw-FPS semantics for providers whose contract actually owns that control.

## 10. Typed final media sandbox

`VideoTimeline` is the only input to final composition.

`FfmpegArgvCompiler` produces argv only; no shell command is built from prompt/user text. Hosted execution uses the remote Sandbox Runtime with network-disabled child execution and bounded CPU/memory/time.

Current V1 final composition produces:

- H.264 MP4;
- fixed requested width/height;
- fixed requested FPS through `-r`;
- bounded requested duration;
- fast-start metadata;
- provider audio omitted unless explicitly represented by a supported timeline audio path.

CROSSFADE remains fail-closed in V1.

## 11. Final durable MP4 verification

The Sandbox bridge's intermediate `RenderedVideo` metadata is **not trusted as final evidence**.

After final MP4 promotion to durable S3, `HostedVerifiedVideoMediaSandbox` independently re-stages and re-probes the durable object through network-disabled `ffprobe`.

Before final Artifact readiness it requires actual-file evidence for:

- durable checksum/size identity;
- MP4 container/MIME;
- H.264 codec;
- requested width/height;
- requested FPS;
- requested duration within tolerance;
- expected audio presence/absence.

The final `RenderedVideo` metadata is rebuilt from the probe result. Timeline-expected width/height/duration cannot self-certify the Artifact.

## 12. Artifact lineage and replay boundary

Every materialized shot attempt receives its own VIDEO ArtifactVersion. Rejected attempts remain auditable.

Final lineage uses canonical edges such as:

```text
shot clip version --COMPOSED_FROM--> final video version
```

Final files point only at durable generated objects.

Artifact persistence and the NODE-48 recovery snapshot are intentionally **not claimed to be one PostgreSQL transaction**. Artifact IDs, branch IDs, version IDs, file IDs, provenance IDs and lineage edge IDs are deterministic UUID5 identities derived from stable operation/provenance inputs. Replaying the same successful materialization therefore converges on the same canonical rows instead of creating duplicate versions or lineage.

The Hosted crash-recovery contract combines that deterministic Artifact replay with deferred provider-output deletion. If the Artifact transaction commits and the later recovery transaction fails, the previous WAITING_EXTERNAL/provider identity remains the recovery source of truth, the provider source object is retained, and retry can re-poll/re-materialize the same provider result into the same Artifact identities. This is a recoverable transaction boundary, not a claim of global atomicity.

## 13. Cost semantics

Every accepted paid provider attempt is reconciled against the canonical NODE-27 ledger by tenant + paid operation scope.

Worker Media is read-only with respect to provider cost truth. It verifies the one canonical `actual_cost` row already written through Model Gateway and does not insert/update/delete `cost_ledger`.

## 14. Public Generation and event UoW

For API-created video operations, `PostgresVideoRepository.flush()` synchronizes the canonical generic `generations` row in the same PostgreSQL transaction as the NODE-48 recovery/provider snapshot.

Hosted lifecycle events do not use an independent immediate transaction. `BufferedVideoEventSink` keeps events invocation-local while the pipeline advances; `PostgresVideoRepository.flush()` inserts those canonical `outbox_events` on the same connection/transaction as recovery/provider/public Generation state. The buffer is cleared only after the transaction context commits successfully. A repository/event database mismatch fails before a PostgreSQL connection is opened.

Public result JSON is sanitized and includes job/shot status, costs and Artifact identifiers. Provider request IDs are intentionally not exposed in the public result.

Internal Agent/TaskGraph video jobs without a public Generation row remain valid and safely no-op that synchronization step while still using the same recovery/event transaction.

## 15. Events and external wait

Current durable lifecycle events include:

```text
video_generation.started
video_generation.external_wait
video_generation.shot_quality_retry
video_generation.shot_ready
video_generation.completed
video_generation.cancelled
```

Events contain identifiers/status/provenance references, not provider credentials or raw video bytes.

The legacy `PostgresVideoEventSink` remains available only as a compatibility adapter for non-Hosted direct use. Hosted production composition must use `BufferedVideoEventSink`; reintroducing `PostgresVideoEventSink(...)` into `HostedVideoGenerationRuntime` is a release-contract failure.

## 16. Performance telemetry

Final media work is wrapped by `TimedMediaSandbox` and emitted under the real POSTPROCESS performance stage. The final durable ffprobe is inside this Hosted media boundary rather than a hidden unmeasured side path.

## 17. Evidence and CI

The dedicated Video Generation workflow requires:

- Hosted source contracts, including buffered event UoW, deferred provider-output cleanup, and provider-reconciled cancellation;
- frozen all-workspace dependency install;
- NODE-48 domain tests;
- Hosted Worker boundary tests;
- cancellation regressions covering unproven cancellation, confirmed cancellation, terminal-race success and invalid reconciliation state;
- deterministic provider-output cleanup regressions;
- PostgreSQL transaction rollback proof for recovery + event UoW;
- PostgreSQL deterministic Artifact replay proof;
- Ruff/Pyright;
- Worker image build/import/liveness smoke;
- PostgreSQL producer/recovery/privilege/public-generation acceptance;
- Model Gateway / Artifact regressions;
- deterministic benchmark.

Synthetic/MockProvider evidence does not certify live visual quality.

## 18. Completion rule

NODE-48 remains **IMPLEMENTED / VALIDATING / not COMPLETE** until:

1. the canonical `uv.lock` includes the full workspace and frozen install passes;
2. hosted contract/quality/integration/image-smoke jobs actually execute green;
3. PostgreSQL and runtime-image evidence is captured from a trusted runnable environment; and
4. approved live provider/model video benchmark snapshots exist for the production-routed model profile.

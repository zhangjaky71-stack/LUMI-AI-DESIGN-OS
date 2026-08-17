# NODE-48 Acceptance — Video Generation & Composition

## Status

**IMPLEMENTED / VALIDATING / not COMPLETE**

This record distinguishes implementation evidence from execution evidence. The current branch contains the NODE-48 control plane, durable runtime adapters, Artifact Engine bridge and automated validation gates. It does **not** claim hosted CI or live provider acceptance green.

## Implemented scope

- provider-neutral five-mode video task and storyboard contracts;
- deterministic initial and retry paid-operation ids;
- long-running `PENDING -> WAITING_EXTERNAL -> resume` lifecycle;
- bounded `resume()` with at most one provider poll per waiting shot per call;
- task-level estimate gate plus per-shot Model Gateway budget cap;
- current NODE-22 `ModelRequest` / `ModelInput` / `RoutingHints` integration in the API layer;
- service package isolation from concrete Model Gateway dependencies;
- feature-registry gating for start frame, continuity reference and camera controls;
- mandatory async submit contract and stable provider/model identity on poll;
- explicit cancellation, unexpected-provider-cancel failure semantics and late-completion discard behavior;
- partial-submit compensation that preserves the original FAILED truth after cleanup;
- staged provider-output fetch, MIME/size/probe/SHA-256/internal-store boundary;
- structured durable video objects with bucket/key/size metadata suitable for Artifact files;
- technical, provider-safety, Identity and Brand fail-closed validation;
- independent failed-shot retry without regenerating READY shots and failed-provider exclusion when known;
- renderer-neutral timeline;
- typed FFmpeg argv compiler with no shell execution and protocol/path/token rejection;
- sandbox resource-limit contract;
- durable `PostgresVideoRepository` for jobs, shots, provider-pending state, clips, cost projection and tenant-scoped webhook dedupe;
- complete job codec for restart recovery;
- NODE-42 VIDEO ArtifactVersion adapter for every READY shot and final composed video;
- final `COMPOSED_FROM` lineage from the final video to all shot ArtifactVersions;
- final provenance with Asset/rights/provider/model/request/ArtifactVersion/AgentRun/recipe/skill/git evidence;
- NODE-27 monetary ownership preserved; NODE-48 stores audit projection only;
- Alembic revision `20260817_0017` directly after NODE-47 `20260817_0016`;
- deterministic lifecycle/security/codec/Artifact/state-edge tests;
- static architecture validator;
- deterministic 2,000-shot planning benchmark harness;
- dedicated contract / quality / PostgreSQL / benchmark workflow;
- five-item production gap ledger.

## Deterministic test intentions

The committed suite covers:

1. stable paid-operation ids and distinct retry ids;
2. Storyboard -> external provider wait -> clips -> final video provenance;
3. failed-shot retry without regenerating a READY shot and failed-provider exclusion;
4. cancellation when a provider cannot immediately cancel and safe discard of late completion;
5. unexpected provider cancellation becoming FAILED instead of a stuck job;
6. FAILED-job cancel idempotency;
7. operation-id idempotency and semantic conflict rejection;
8. tenant-scoped duplicate webhook claim rejection;
9. transient poll failure remaining resumable;
10. Identity/Brand validator fail-closed behavior;
11. provider safety and black-frame hard rejection;
12. FFmpeg argv-only execution contract and network/protocol/token rejection;
13. durable video object rejection of public/signed URL truth;
14. completed-job persistence codec round trip;
15. NODE-42 VIDEO Artifact contract, provider/source provenance and final `COMPOSED_FROM` lineage.

These are committed test intentions until an execution environment actually runs them.

## Hosted gates and observed execution evidence

The NODE-48 workflow requires all of the following to execute green before hosted acceptance:

- `video-contract`
- `video-quality`
- `video-db`
- `video-benchmark`

GitHub Actions run `32044867683` was created for PR #115, proving the workflow registered and triggered. Its first job (`95430440517`, `video-contract`) did **not** start any step. GitHub rejected the job before runner startup because recent account payments had failed or the account spending limit needed to be increased. Therefore this run is infrastructure-blocked, not a NODE-48 code failure, and it provides no pytest/Ruff/Pyright/PostgreSQL green or red evidence.

The PostgreSQL gate is authored to migrate the complete schema to Alembic head and verify the NODE-48 runtime tables plus Artifact/storage binding columns once hosted execution is available.

## Production completion gates

NODE-48 remains **not COMPLETE** until all five gap-ledger items are resolved. In particular, mock/control-plane tests do not certify real provider video quality. Selected live provider/model revisions must be approved for motion quality, start-frame adherence, product/logo/character consistency, brand continuity, latency, cost, fallback and cancellation semantics.

The implemented NODE-42 bridge still needs real database/object-storage crash/retry idempotency acceptance, and production NODE-43/NODE-44 validators still need sampled-frame calibration.

## Files

- `services/video-generation/src/lumi_video_generation/*`
- `services/video-generation/tests/*`
- `apps/api/src/lumi_api/video_generation/*`
- `apps/api/src/lumi_api/persistence/models_video_generation.py`
- `apps/api/migrations/versions/20260817_0017_video_generation.py`
- `apps/api/migrations/versions/20260817_0017_sql/*`
- `tools/node48/*`
- `docs/runtime/VIDEO-GENERATION-V1.md`
- `reports/nodes/NODE-48/gap-ledger.json`
- `.github/workflows/node-48-video-generation.yml`

## Next node

After NODE-48 implementation validation, proceed to **NODE-49 — Export Engine** while keeping NODE-48 production gaps visible and unclosed.

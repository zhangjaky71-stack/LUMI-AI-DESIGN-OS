# NODE-48 Acceptance — Video Generation & Composition

## Status

**IMPLEMENTED / VALIDATING / not COMPLETE**

This record distinguishes implementation evidence from execution evidence. The current branch contains the NODE-48 control plane and its automated validation gates, but this acceptance file does not claim that the newly authored hosted jobs or live provider tests have passed.

## Implemented scope

- provider-neutral five-mode video task and storyboard contracts;
- deterministic initial and retry paid-operation ids;
- long-running `PENDING -> WAITING_EXTERNAL -> resume` lifecycle;
- bounded `resume()` with at most one poll per waiting shot per call;
- task-level estimate gate plus per-shot Model Gateway budget cap;
- current NODE-22 `ModelRequest` / `ModelInput` / `RoutingHints` integration;
- feature-registry gating for start frame, continuity reference and camera controls;
- mandatory async submit contract and stable provider/model identity on poll;
- explicit cancellation with late-completion discard behavior;
- staged provider-output fetch, MIME/size/probe/SHA-256/internal-store boundary;
- technical, provider-safety, Identity and Brand fail-closed validation;
- independent failed-shot retry without regenerating READY shots;
- renderer-neutral timeline;
- typed FFmpeg argv compiler with no shell execution and protocol/path rejection;
- sandbox resource-limit contract;
- shot/final Artifact append ports preserving NODE-42 ownership;
- final provenance with Asset/rights/provider/model/AgentRun/recipe/skill/git evidence;
- NODE-27 monetary ownership preserved; NODE-48 stores audit projection only;
- Alembic revision `20260817_0017` directly after NODE-47 `20260817_0016`;
- deterministic lifecycle/security tests;
- static architecture validator;
- deterministic 2,000-shot planning benchmark harness;
- dedicated contract / quality / PostgreSQL / benchmark workflow;
- five-item production gap ledger.

## Deterministic test intentions

The committed suite covers:

1. stable paid-operation ids and distinct retry ids;
2. Storyboard -> external provider wait -> clips -> final video provenance;
3. a failed shot retry without regenerating a READY shot;
4. cancellation when a provider cannot immediately cancel and safe discard of a late completion;
5. operation id idempotency and semantic conflict rejection;
6. duplicate webhook claim rejection;
7. Identity/Brand validator fail-closed behavior;
8. provider safety and black-frame hard rejection;
9. FFmpeg argv-only execution contract and network/protocol input rejection.

## Hosted gates

The NODE-48 workflow requires all of the following to actually execute green before hosted acceptance:

- `video-contract`
- `video-quality`
- `video-db`
- `video-benchmark`

The PostgreSQL job migrates the complete schema to Alembic head and checks the NODE-48 tables exist.

## Production completion gates

NODE-48 must remain **not COMPLETE** until all five gap-ledger items are resolved. In particular, synthetic/mock tests do not certify real provider video quality. Selected live provider/model revisions must be approved for motion quality, start-frame adherence, product/logo/character consistency, brand continuity, latency, cost, fallback and cancellation semantics.

## Files

- `services/video-generation/src/lumi_video_generation/*`
- `services/video-generation/tests/*`
- `apps/api/migrations/versions/20260817_0017_video_generation.py`
- `apps/api/migrations/versions/20260817_0017_sql/*`
- `tools/node48/*`
- `docs/runtime/VIDEO-GENERATION-V1.md`
- `reports/nodes/NODE-48/gap-ledger.json`
- `.github/workflows/node-48-video-generation.yml`

## Next node

After NODE-48 implementation acceptance, proceed to **NODE-49 — Export Engine** while keeping NODE-48 production gaps visible and unclosed.

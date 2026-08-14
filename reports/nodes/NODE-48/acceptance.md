# NODE-48 Acceptance — Video Generation & Composition

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-47-image-edit-release`

## Acceptance matrix

| Requirement | Evidence | Status |
|---|---|---|
| Text-to-video contract | `VideoTaskSpec`, Model Gateway adapter | Implemented |
| Image-to-video contract | source version/checksum + feature registry | Implemented |
| Multi-shot storyboard | `storyboard.py`, pipeline | Implemented |
| External-wait long task | `WAITING_EXTERNAL`, `resume()` | Implemented |
| No worker sleep loop | pipeline/static validator | Implemented |
| One poll per resume | pipeline + executable test | Implemented |
| Provider submit/poll/cancel | NODE-22 adapter + real MockProvider test | Implemented |
| Provider feature facts | `VideoFeatureRegistry` | Implemented |
| Exact provider allowlist | NODE-22 routing gate | Implemented |
| Quality retry provider exclusion | pipeline/router/adapter | Implemented |
| New paid operation per retry | UUIDv5 retry IDs | Implemented |
| Terminal provider attempt retention | repository + SQL | Implemented |
| Crash replay after provider completion | archived terminal result contract | Implemented |
| Cumulative task budget | pipeline + test | Implemented |
| Cost on failed/rejected output | terminal cost before postflight | Implemented |
| Cost idempotency | paid-operation ledger key | Implemented |
| Optional-shot explicit drop | PARTIAL semantics + test | Implemented |
| Previous-tail continuity | pipeline + lineage test | Implemented |
| Source/reference continuity | `ContinuityRef` | Implemented |
| Identity keyframe validation | NODE-44 delegate contract | Implemented |
| Brand keyframe validation | NODE-43 delegate contract | Implemented |
| Validator unavailable fail-closed | validator + test | Implemented |
| Decode/MIME/resolution/FPS/duration gates | `validation.py` | Implemented |
| Per-attempt VIDEO Artifact | Artifact adapter | Implemented |
| Rejected attempts preserved | paid-operation-bound Artifact IDs | Implemented |
| Final VIDEO Artifact | Artifact adapter | Implemented |
| COMPOSED_FROM lineage | Artifact adapter + test | Implemented |
| Poster/tail/keyframe references | clip contract/provenance | Implemented |
| Thumbnail/subtitle file contracts | final Artifact adapter | Implemented |
| Typed VideoTimeline | `model.py` | Implemented |
| FFmpeg argv-only compilation | `media_sandbox.py` | Implemented |
| Trusted sandbox path resolver | `/sandbox/` path gate | Implemented |
| Network-disabled sandbox requirement | `SandboxLimits` | Implemented |
| No domain subprocess fallback | static validator | Implemented |
| Multi-track audio offset/gain/mix | typed FFmpeg filters | Implemented |
| Unsupported CROSSFADE fail-closed | compiler + test | Implemented V1 boundary |
| PostgreSQL persistence | `0007_video_generation.sql` | Implemented |
| 48-case synthetic matrix | conformance fixture | Implemented synthetic evidence |
| Dependency-free planning benchmark | benchmark script | Implemented; hosted execution pending |
| Dedicated four-stage CI | workflow | Implemented; hosted execution pending |
| Live provider visual-quality benchmark | provider benchmark report | **Pending** |

## Safety and correctness assertions

1. Provider-native requests and credentials remain behind NODE-22.
2. Video provider wait time never occupies a sleeping LangGraph/queue worker.
3. Provider completion identity is pinned to provider/model/request/paid-operation.
4. A quality retry is a new paid operation and re-enters budget control.
5. A retry excludes the provider/model that produced the rejected attempt.
6. Hard Brand/Identity/technical requirements are not weakened to obtain success.
7. Optional shots may be dropped only when explicitly marked optional and policy enables it.
8. Rejected attempt Artifacts are append-preserved and cannot be overwritten by the successful retry.
9. Provider URLs are not durable file truth; Artifact storage key/checksum is.
10. FFmpeg execution receives typed argv and sandbox-resolved paths; no user-controlled shell command exists.
11. Terminal provider-job rows are retained for crash-safe replay.
12. Cost reconciliation happens before downstream acceptance and is idempotent by paid operation.

## Synthetic evidence honesty

The 48-case conformance matrix and MockProvider tests validate state, routing, retry, cost, validation, lineage and sandbox contracts. They do **not** demonstrate real provider video fidelity.

## Live provider benchmark blocker

Production routing remains gated until selected provider/model revisions have approved NODE-23 evidence for:

```text
text_to_video_prompt_adherence
image_to_video_first_frame_fidelity
product_identity_continuity
character_identity_continuity
logo_brand_continuity
multi_shot_temporal_continuity
camera_control_accuracy
duration_fps_resolution_accuracy
provider_latency_and_queue_time
cost_accuracy
cancellation_behavior
fallback_and_quality_retry
```

No live score is fabricated by NODE-48.

## Lockfile discipline

`services/video-generation` introduces no external Python dependency and is not hand-added to the root workspace lock. Root `uv.lock` must remain unchanged. Dedicated CI runs it through the frozen root development environment plus explicit `PYTHONPATH`.

## Hosted validation requirement

Required jobs:

```text
video-generation-contract
video-generation-quality
video-generation-integration
video-generation-benchmark
```

If GitHub returns the known account-level billing/spending-limit zero-step failure, record it as an external validation blocker. It is neither PASS nor an observed code/test failure.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Blocking completion evidence:

1. hosted NODE-48 jobs must actually execute green;
2. selected live video provider/model revisions need approved benchmark snapshots.

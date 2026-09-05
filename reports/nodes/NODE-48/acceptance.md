# NODE-48 Acceptance — Video Generation & Composition

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## Acceptance matrix

| Requirement | Canonical evidence | Status |
|---|---|---|
| Public `video.generate` producer | `VideoGenerationControlPlane` + PostgreSQL producer acceptance | Implemented |
| Canonical `video.render` dispatch | Task + outbox + dispatcher integration | Implemented |
| Hosted text-to-video | private Model Gateway + OpenAI async adapter | Implemented |
| Hosted image-to-video | controlled Asset-to-provider boundary | **Fail-closed / not exposed** |
| Hosted multi-shot | production continuity/reference boundary | **Fail-closed / not exposed** |
| External-wait long task | TaskJobStore + `WAITING_EXTERNAL` + wake scheduler | Implemented |
| No worker sleep loop | NODE-48 pipeline | Implemented |
| One provider poll per resume | pipeline contract/tests | Implemented |
| Stable paid operation identity | NODE-20 + shot paid operation IDs | Implemented |
| Provider job crash recovery | `video_generation_jobs` / `video_provider_jobs` snapshots | Implemented |
| Provider-reconciled cancellation | `VideoGenerationPipeline.cancel/resume` + Hosted runtime + static cancellation contract | Implemented source; Hosted execution evidence blocked |
| Runtime recovery rows not physically deleted | Alembic 0023 privilege contract | Implemented |
| Canonical provider cost truth | tenant-scoped NODE-27 reconciliation | Implemented |
| Worker cannot mutate `cost_ledger` | source + PostgreSQL privilege acceptance | Implemented |
| Provider output private staging | provider-output S3 contract | Implemented |
| Worker binary download avoided | S3 server-side copy + Sandbox exchange | Implemented |
| Raw provider ffprobe | network-disabled Sandbox | Implemented |
| Raw decode/MIME/resolution/duration/safety gates | `HostedV1VideoValidator` | Implemented |
| Raw provider FPS not treated as controllable output FPS | Hosted FPS ownership contract | Implemented |
| Typed final FFmpeg composition | `FfmpegArgvCompiler` / remote Sandbox | Implemented |
| Final durable MP4 independent ffprobe | `HostedVerifiedVideoMediaSandbox` | Implemented |
| Final H.264/container/resolution/FPS/duration enforcement | final probe contract/tests | Implemented |
| Final VIDEO Artifact | canonical Artifact adapter | Implemented |
| `COMPOSED_FROM` lineage | PostgreSQL acceptance | Implemented |
| Public Generation state sync | Worker repository transaction + PostgreSQL acceptance | Implemented |
| Public result hides provider request ID | sanitized Generation result contract | Implemented |
| Hosted recovery schema | Alembic `0023_video_generation_runtime` | Implemented |
| Historical parallel NODE-48 tables absent | Video integration SQL assertion | Implemented contract; execution evidence pending |
| Worker runtime image provenance includes full Hosted Video chain | runtime manifest + NODE-71 negative drills | Implemented |
| Video package is canonical uv workspace member | root `pyproject.toml` | Implemented source; lock regeneration pending |
| Dedicated five-job CI | Video Generation workflow | Implemented; hosted runner execution blocked |
| Live provider visual-quality benchmark | provider benchmark evidence | **Pending** |

## Hosted production boundary

The provider-neutral domain model can express image-to-video and multi-shot storyboard behavior, but current Hosted V1 intentionally accepts only single-shot `TEXT_TO_VIDEO` with the supported 4/8/12-second provider duration contract.

Hosted V1 fails closed on:

- source/reference images;
- continuity refs;
- separate audio tracks;
- Identity requirements;
- Brand Rule Sets;
- seed;
- negative prompt;
- camera-motion / subject-action provider controls;
- optional/multi-shot production execution.

Domain expressiveness is not evidence that the Hosted production path exposes a feature.

## Safety and correctness assertions

1. Provider credentials/native payloads remain behind Model Gateway.
2. Provider wait time never occupies a sleeping Worker/LangGraph task.
3. Provider completion identity is pinned to provider/model/request/paid-operation state.
4. Provider output enters Worker only as a bounded private S3 reference.
5. Raw media is probed inside a network-disabled Sandbox boundary.
6. Raw provider FPS is observational metadata for Hosted V1; it is not an uncontrollable post-payment rejection gate.
7. Final FPS is normalized by typed FFmpeg and independently re-probed from the promoted durable final MP4.
8. Intermediate timeline-expected width/height/duration metadata cannot self-certify final Artifact readiness.
9. Every accepted provider attempt keeps canonical NODE-27 cost truth even when quality validation later fails.
10. Worker Media is read-only with respect to provider cost truth.
11. Video recovery/provider-attempt rows are retained; runtime DELETE privilege is absent.
12. Artifact files/edges/provenance remain canonical append-preserved truth.
13. Public Generation results do not expose provider request IDs.
14. Production cancellation remains fail-closed until provider cancellation semantics are proven rather than inferred from deletion.
15. A Provider cancel transport exception or timeout does not self-certify cancellation: the job remains `WAITING_EXTERNAL`, the original provider recovery row remains authoritative, and the next cancellation reconciliation polls that same provider request at most once.
16. If the original Provider request has already succeeded, terminal Provider truth wins the cancellation race: the successful output is materialized/validated/composed and no replacement `estimate` or `submit` is allowed.
17. Cancellation reconciliation uses `resume(..., allow_quality_retry=False)` so Provider failure, postprocess failure, or validation failure after cancellation intent cannot create a second paid quality-retry request.

## Persistence truth

Hosted production does **not** use the historical seven-table `0007_video_generation.sql` model as its runtime source of truth.

Canonical Hosted recovery tables are created by Alembic `0023_video_generation_runtime`:

```text
video_generation_jobs
video_provider_jobs
```

The rest of the state is reused from canonical subsystems:

```text
tasks / TaskJobStore
generations
idempotency_operations
cost_ledger
artifact / branch / version / file / provenance / edge tables
outbox_events
```

The Video integration gate explicitly requires exactly the two Hosted recovery tables and requires the historical parallel NODE-48 tables to be absent.

## FPS ownership acceptance

`VideoTaskSpec.fps` remains a material semantic input and final-output requirement.

For current Hosted provider execution, raw provider FPS is not a provider create control. Therefore:

- a raw provider clip at 30 FPS can pass raw validation for a 24 FPS final task when decode/MIME/resolution/duration/safety are valid;
- typed FFmpeg renders the final output at 24 FPS;
- the promoted final MP4 must independently ffprobe at 24 FPS or the job fails before final Artifact readiness.

This avoids an unnecessary paid retry for an uncontrollable raw property without weakening final media correctness.

## Runtime image provenance

Worker Media accepted-image provenance must contain both Image and Hosted Video execution sources, including:

- `services/video-generation`;
- Worker Dockerfile/entrypoint and job runtime;
- Video gateway/codec/repository/ports/artifacts/runtime;
- Sandbox bridge;
- final durable probe runtime;
- Hosted raw-validation runtime;
- scoped cost observer;
- external-wait/event/dispatch runtime.

NODE-71 Staging Acceptance drills removal of every required Worker media source. NODE-71 downloaded decision validation repeats the Hosted Video provenance requirement before Production/Final can consume it.

## Lockfile discipline

`services/video-generation` is now a **canonical root uv workspace member** and both API and Worker Media declare `lumi-video-generation` as a production dependency.

The checked-in `uv.lock` is currently stale because its manifest does not yet contain `lumi-video-generation`. This is an explicit blocker.

The lock must be regenerated only through the canonical two-phase resolver workflow:

```text
uv lock
-> validate_uv_workspace_lock.py
-> uv lock --check
-> uv sync --all-packages --frozen
-> isolated commit of uv.lock only
```

The lock must not be hand-edited.

## Required Hosted CI

The current Video Generation workflow requires:

```text
video-generation-contract
video-generation-quality
worker-media-video-smoke
video-generation-integration
video-generation-benchmark
```

Quality includes all Hosted Worker `test_video_*.py` tests plus Ruff/Pyright. Integration includes API producer/outbox and Worker PostgreSQL recovery/privilege/public-generation acceptance.

The cross-node Model Gateway and Artifact regressions execute inside the Video integration job.

## Cancellation recovery regression closure

The provider-neutral cancellation suite now explicitly locks both terminal-race and transport-failure behavior:

- `test_successful_provider_truth_wins_over_cancellation_intent` proves a Provider `SUCCEEDED` truth is preserved through cancellation reconciliation, produces a final Artifact, records terminal cost once, emits completion rather than cancellation, and performs zero replacement `estimate`/`submit` calls.
- `test_cancel_transport_error_reconciles_original_provider_success_without_retry` proves a cancel API exception preserves the original `PENDING` provider recovery row, the next reconciliation polls the same `provider_request_id` exactly once, accepts `SUCCEEDED`, and performs zero replacement `estimate`/`submit` calls.
- `scripts/validate_video_cancellation_contract.py` requires both regressions plus the single-poll/original-request/no-replacement evidence markers, so removal of these protections blocks the static Video/Final source gates.

## Hosted runner evidence status

Latest sampled PR head: `c8147dec26c3a93f54fa96a91168427543c2edcb`.

Video Generation run `32454884400` still failed before any executable step began:

- `video-generation-contract` job `96690155600`: `failure`, `steps=null`, `logs_url=null`;
- `video-generation-quality`: skipped;
- `video-generation-benchmark`: skipped;
- `worker-media-video-smoke`: skipped;
- `video-generation-integration`: skipped.

The same PR head also shows the broader release gates failing before executable evidence:

- Production IaC Contract run `32454884297`: `source-contract` job `96690155400`, `terraform-static` job `96690155650`, and `contract-gate` job `96690167927` all failed with no job steps/log URL exposed;
- Final Product Acceptance Gate run `32454884358`: `canonical-lock-gate` job `96690155354`, `source-contract` job `96690155541`, and `node73-final-contract-gate` job `96690167278` failed with no job steps/log URL exposed; `final-decision` was skipped.

This remains consistent with the existing GitHub-hosted runner/account/scheduling blocker. These red checks are:

- not evidence of a Python/Ruff/Pyright/pytest/PostgreSQL/Docker/Terraform application failure; and
- not PASS evidence.

No checkout, Python, `uv`, Docker, pytest, PostgreSQL, Terraform, or application command is evidenced as having executed for this head. No final acceptance claim is made from zero-step runs.

## Synthetic evidence honesty

Synthetic/domain tests validate state-machine, routing, retry, cost, validation, lineage and sandbox contracts. They do **not** demonstrate real provider video fidelity.

## Live provider benchmark blocker

Production routing remains gated until the exact configured provider/model profile has approved live evidence for prompt adherence, technical output, latency/queue time, cost accuracy, provider failure behavior and any production-exposed continuity/control features.

No live score is fabricated by NODE-48.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Blocking completion evidence:

1. canonical `uv.lock` must be resolver-regenerated and frozen all-workspace sync must pass;
2. Hosted NODE-48 jobs must actually execute with step/log evidence and pass;
3. PostgreSQL and Worker image build/import/liveness evidence must execute successfully;
4. exact accepted Worker runtime-image provenance/attestations must be captured;
5. selected production-routed video provider/model revisions need approved live benchmark snapshots;
6. NODE-71/72 staging and production evidence must close before NODE-73 can pass.

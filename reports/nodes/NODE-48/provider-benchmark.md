# NODE-48 Live Provider Benchmark

Status: **PENDING — no live provider score is claimed in NODE-48 implementation**

The synthetic fixture, MockProvider integration and deterministic worker tests prove orchestration behavior only. They do not prove production video-model quality.

## Required benchmark matrix before production routing

Every selected `provider:model@revision` must have an approved NODE-23 benchmark snapshot for at least:

| Profile | Minimum evidence |
|---|---|
| text-to-video prompt adherence | representative product/brand prompts |
| image-to-video first-frame fidelity | source-image visual preservation |
| product identity continuity | NODE-44 calibrated identity evidence across keyframes |
| character identity continuity | approved keyframe continuity set |
| logo / brand continuity | NODE-43 compliance + readable wordmark/logo evidence |
| multi-shot temporal continuity | previous-tail / explicit-reference cases |
| camera control accuracy | supported camera-control scenarios only |
| duration / FPS / resolution accuracy | decoded output probes |
| queue + end-to-end latency | provider submit-to-terminal timestamps |
| cost accuracy | estimate vs reconciled actual |
| cancellation | accepted cancellation and terminal semantics |
| fallback / quality retry | distinct paid operations and alternate-provider evidence |

## Benchmark rules

1. Provider revision, feature-registry snapshot and pricing snapshot must be pinned.
2. Identity thresholds come from NODE-44 calibration profiles; they are not invented here.
3. Brand evaluation uses the exact NODE-43 rule-set version.
4. Queue time and inference time are reported separately when the provider exposes them.
5. Failed, blocked and corrupt outputs remain in denominator and cost reconciliation.
6. A provider cannot be promoted because only successful samples were retained.
7. Optional-shot drop is a workflow policy, not a quality success.
8. Synthetic MockProvider results never satisfy this gate.

## Current decision

**PENDING**. Production video routing remains disabled until approved live evidence exists.

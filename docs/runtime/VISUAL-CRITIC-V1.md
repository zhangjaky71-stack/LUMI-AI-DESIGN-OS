# Visual Critic Runtime V1

## Purpose

Visual Critic is LUMI's post-generation quality decision layer. It answers three questions for an **exact** Artifact/Design version:

1. Is this version safe and acceptable for the selected QualityProfile?
2. Which evidence caused the decision?
3. Which known issues can be expressed as typed repair operations for NODE-51?

It does not execute repairs and does not approve Artifact status.

## Runtime package

```text
packages/quality-engine/
├─ src/types.ts
├─ src/profiles.ts
├─ src/ports.ts
├─ src/deterministic.ts
├─ src/calibration.ts
├─ src/engine.ts
├─ src/artifact-adapter.ts
├─ src/observability.ts
└─ tests
```

## Input

`CriticSubject` pins:

```text
organization_id
project_id
artifact_id
artifact_version_id
design_document_version_id
exact DesignDocument
rendered_asset_ref
rendered width/height
expected_text[] optional
quality metadata optional
```

Callers must not pass a floating latest/head alias as an exact version identity.

## Evaluation order

The runtime deliberately evaluates high-certainty signals before subjective signals:

```text
1 deterministic Design IR / metadata
2 NODE-39 constraint report
3 NODE-43 brand report
4 NODE-44 identity report
5 OCR
6 QR decoder
7 independent calibrated visual grader
8 profile aggregation
9 Artifact/DB record
```

Later signals cannot erase earlier hard violations.

## Deterministic graders

V1 programmatic graders include:

### Text overflow

Uses exact node bounds and measured text metadata. Overflow emits `TYPOGRAPHY_READABILITY` plus a `RESIZE_NODE` proposal.

### Parent bounds

Detects visible child geometry extending beyond an exact parent box and proposes a bounded `MOVE_NODE`.

### Contrast

For exact `#RRGGBB` foreground/background metadata, calculates WCAG-style relative luminance/contrast ratio. This signal is deterministic, but V1 does not pretend to infer arbitrary image-background contrast without a real image sampler.

### Text accuracy

When `expected_text` is supplied, Design IR text is compared exactly. A single expected text / single text-node mismatch may propose `SET_TEXT`; ambiguous multi-node copy is not guessed.

### Export resolution

When minimum dimensions are part of the quality metadata, insufficient rendered size becomes a hard signal.

## Constraint delegation

NODE-50 does not reimplement locks or protected-region semantics. `ConstraintQualityPort` consumes NODE-39 `PostflightReport`.

Important mappings include:

```text
REQUIRE_SCANNABILITY     -> QR_READABILITY
REQUIRE_CONTRAST         -> CONTRAST
REQUIRE_TEXT_READABILITY -> TYPOGRAPHY_READABILITY
REQUIRE_BRAND_COMPLIANCE -> BRAND_CONSISTENCY
REQUIRE_IDENTITY_SCORE   -> IDENTITY_CONSISTENCY
REQUIRE_RESOLUTION       -> RESOLUTION_EXPORT_READINESS
other constraints        -> CONSTRAINT_COMPLIANCE
```

Hard constraint failure is always `FAIL_HARD`. If the required runtime is unavailable, active hard-gate evidence has insufficient confidence and the result is blocked in `REVIEW_REQUIRED` rather than falsely passing.

## Brand delegation

`BrandQualityPort` consumes NODE-43 `BrandComplianceReport`. Hard brand rules remain hard. Logo-category diagnostics also feed `LOGO_INTEGRITY`.

NODE-43 `repair_operations` are passed through only when they are valid current-version NODE-38 DesignOperations.

## Identity delegation

`IdentityQualityPort` consumes NODE-44 `IdentityValidationReport[]`.

For product/logo preservation:

```text
HARD + FAIL -> FAIL_HARD
REVIEW       -> confidence/review path
UNAVAILABLE  -> confidence/review path
PASS         -> contributes calibrated score/confidence
```

Aesthetic VLM score never overrides a hard identity failure.

## OCR and QR

OCR is a normalized port. The Quality Engine compares expected text and confidence; provider-specific schemas stay outside the package.

QR requires more than visual presence:

```text
detected
payload_matches
readable_at_target_size
quiet_zone_ok optional
confidence
```

A configured QR hard failure cannot be compensated by composition score.

## Visual grader

`VisualGraderPort` is deliberately narrow and provider-neutral.

Required identity:

```text
grader_id
grader_version
role_id = visual-critic
model_provider
model_name
model_version
prompt_version
calibration_dataset_version
```

Production adapters must call NODE-22 Model Gateway. The Quality Engine package must not import provider SDKs or own API keys.

### Isolation

If generation context reports the same `provider/model@version` and the same prompt version as the critic grade, that grade is not allowed to approve. It is marked unavailable as `visual-grader:not-isolated`.

Using a separate role/prompt is mandatory; a separate model is strongly preferred for high-impact profiles.

### Timeout and failure

Visual grading has a bounded timeout. Failure is not converted to zero as though a judgment occurred; the grader is marked unavailable and an active profile depending on it routes to review.

## Calibration

A visual grade is accepted only when an approved `HumanCalibrationSummary` exactly matches:

```text
grader_id
grader_version
calibration_dataset_version
```

Calibration records include:

```text
sample_count
precision
recall
F1
false positive rate
false negative rate
inter-rater agreement
approved
```

V1 code requires at least 20 samples and rejects an approved calibration with F1 < 0.60 or inter-rater agreement < 0.50. These are minimum contract safeguards, not sufficient production quality criteria by themselves.

The committed fixture is synthetic and tests calibration math only. Live auto-approval requires a real blinded human-labeled corpus and versioned review.

## Quality profiles

Profiles select **applicable** dimensions rather than scoring every possible dimension for every design.

### exploration

Emphasizes composition/hierarchy with a hard constraint floor.

### production-web

Emphasizes constraint safety, hierarchy, typography, text correctness, QR when required, image quality and output resolution.

### brand-strict

Activates Brand and Logo hard gates plus typography/composition quality.

### product-strict

Activates Product Identity as a top-priority hard gate.

### print

Emphasizes exact constraints, resolution, text/contrast and QR where present. Export color-management truth remains owned by NODE-49; NODE-50 cannot claim CMYK support.

### social-fast

Lower subjective thresholds but retains hard constraint safety.

## Score and status

Scores are 0–100; confidence is 0–1.

Per-dimension multi-signal score is confidence-weighted, but any hard signal forces that dimension to zero and marks it hard.

Overall score is weight-based across active profile dimensions.

Status ordering is deliberate:

```text
1 FAIL_HARD
2 REVIEW_REQUIRED for insufficient high-impact confidence
3 PASS
4 PASS_WITH_WARNINGS
5 FAIL_REPAIRABLE
6 REVIEW_REQUIRED fallback
```

This ordering prevents a high average score from hiding safety/identity/brand/QR hard failures.

## Repair actions

QualityResult `repair_actions` contains only frozen NODE-38 `DesignOperation` values. Runtime filters:

- unsupported operation types；
- stale `expected_document_version`；
- semantic duplicates。

Critic never calls `executeOperations`, never runs image editing, never moves a branch head and never loops.

NODE-51 owns:

```text
RepairPlanner
preflight
execution
budget
iteration cap
re-evaluation
rollback
lineage
```

## QualityResult persistence

Full result persistence is separate from Artifact summary metadata.

`ArtifactEngineQualityAdapter` verifies exact organization/project/artifact/version/design version, persists the QualityResult through a repository, then stores `overall_score / 100` in the historical ArtifactVersion `quality_score` field.

It does not change:

```text
content_hash
constraint_snapshot_hash
status
branch head
files
provenance content
```

## PostgreSQL

Migration `0009_visual_critic.sql` adds:

```text
quality_profiles
quality_grader_calibrations
quality_results
quality_dimension_results
quality_violations
quality_evidence
```

`quality_results` references exact ArtifactVersion and exact profile version. A trigger mirrors the 0–100 score into Artifact's existing 0–1 summary scale.

A production repository must insert result, dimensions, violations and evidence transactionally.

## Observability

`qualityMetricSnapshot()` exposes only safe operational fields:

```text
quality_result_id
org/project/artifact version
profile/version
status
score/confidence
hard violation count
repair count
unavailable grader count
evidence/dimension counts
```

Do not log full prompts, OCR text, user image URLs or raw VLM output by default.

## NODE-05 benchmark integration

Offline suite:

```text
visual-critic@1.0.0
```

Cases include:

```text
hard QR
hard brand font
hard product identity
typography repair
grader timeout
low confidence
same-model/prompt self approval
clean deterministic pass
```

The replay suite does not claim live-provider quality. Live/provider/human evaluation remains an explicit separate gate.

## CI gates

```text
critic-contract
critic-quality
critic-integration
critic-calibration
critic-db
critic-benchmark
```

NODE-50 cannot be marked COMPLETE until these jobs actually execute green on the release head. A GitHub Actions billing/spending-limit error with no runner steps is an external validation blocker only.

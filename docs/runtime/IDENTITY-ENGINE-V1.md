# Identity Engine V1 — NODE-44

## Purpose

Identity Engine answers **“is this still the same product/logo/character?”**. It is deliberately separate from visual quality/style criticism. P0 support is PRODUCT and LOGO; CHARACTER is contract-ready P1. FACE is privacy-gated and does not create a cross-tenant or global biometric index.

## Reference Set

A reference set is versioned and immutable by content. Each version carries canonical Asset IDs, reference views, a threshold profile, snapshot hash, actor/time metadata and project/brand scope. PostgreSQL migration `20260817_0013` enforces immutable version rows with a database trigger.

## Multi-signal scoring

LOGO uses independent exact hash, perceptual, local feature and optional OCR/wordmark signals. PRODUCT uses multimodal embedding, local feature, shape/color, detected brand/logo region and optional structured VLM comparison. Missing signals are not silently converted to zero; available weights are re-normalized and signal coverage contributes to confidence.

A high similarity score cannot hide poor target evidence. Final confidence multiplies signal coverage, weighted signal confidence, crop quality and target-detection confidence.

## Region evidence

When a Design IR node provides bounds, the adapter can emit `DESIGN_IR_BOUNDS` evidence directly. Whole-image generation requires a detector/VLM region-proposal adapter. Every validation result records the region and evidence refs used for the decision.

## Threshold profiles

Thresholds are versioned by scenario rather than hard-coded globally. Examples include locked retouch, background replacement, creative redraw and advisory reference use. HARD profiles fail closed when the target is missing, the validator is unavailable, required signals are missing, confidence is insufficient or score is below threshold.

## Calibration

The deterministic calibration runtime consumes positive, negative and near-miss samples. It evaluates observed candidate thresholds, computes precision, recall, false-accept rate, false-reject rate and F1, then selects the highest-recall threshold satisfying the target precision when possible. Dataset content is SHA-256 hashed and the report is versioned.

The generated deterministic report is persisted at `reports/nodes/NODE-44/calibration-report.json`. The repository fixture benchmark is a contract corpus, not a claim of production model accuracy. Real provider/model thresholds remain a production gate.

## NODE-18 / NODE-45 integration boundaries

`Node18IdentityAssetPolicy` enforces tenant/access, READY state and image/vector media suitability before an Asset can enter a reference set. FACE additionally rejects references whose rights assertion is UNKNOWN.

`Node45AssetIntelligenceSignalProvider` consumes versioned Asset Intelligence analysis records and derives exact hash, perceptual hash, OCR, local-feature, multimodal embedding, shape/color and brand-region signals. Exact checksum equality is strong positive evidence; checksum inequality is treated as unavailable for identity rather than negative proof because valid rasterization/compression changes bytes. Multiple canonical reference views are evaluated and the best available score is retained per signal. FACE is intentionally rejected on this persistent Asset Intelligence path.

## Constraint Engine bridge

`IdentityEvidenceScoreAdapter` is a NODE-39 `IdentityScore`-compatible callable. It exposes the exact NODE-44 validation score for a Design IR node. Missing evidence returns `None`; NODE-39 already treats unavailable HARD identity validation as blocking under its fail-closed policy.

## Persistence

`20260817_0013` adds:

- `identity_reference_sets`
- `identity_reference_set_versions`
- `identity_validation_records`
- `identity_calibration_reports` (tenant-qualified report contract + persisted organization ID)

Reference versions are immutable. Validation records retain score, confidence, profile, signal scores, region, evidence refs, failure codes and provider version. No face embedding table exists.

## Privacy

FACE requires explicit authorization and project scope. Brand/global FACE scope is rejected by service and database check. A database scope guard also requires referenced Project/Brand rows to belong to the same organization. The engine does not support a cross-tenant face index or use identity features for unrelated inference.

## API

Authenticated v1 facade:

- `POST /api/v1/identity/reference-sets`
- `POST /api/v1/identity/reference-sets/{identity_id}/versions`
- `GET /api/v1/identity/reference-sets/{identity_id}`
- `POST /api/v1/identity/reference-sets/{identity_id}/validate`
- `POST /api/v1/identity/compare`
- `POST /api/v1/identity/calibration-reports`

The service also exposes internal `compare(reference, candidate, profile)` for direct pair/reference comparisons.

## Production qualification

Five explicit production gaps remain in `reports/nodes/NODE-44/gap-ledger.json`. Hosted CI and real provider/PostgreSQL evidence must not be inferred from deterministic local fixtures.

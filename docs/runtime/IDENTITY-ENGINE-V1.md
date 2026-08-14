# LUMI Identity Engine V1

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

NODE-44 answers one narrow production question: after generation or editing, is a protected product, logo, character, or explicitly permitted face still the same identity?

## Runtime boundary

Identity Engine does **not** upload or authorize assets, mutate Design IR, search the global asset corpus, or independently block an artifact. It consumes NODE-18 READY/verified assets and optional versioned analyzer signals, produces identity evidence/reports, plugs into NODE-39 `IdentitySimilarityValidator`, and supplies an aggregate identity validation snapshot to NODE-42 Artifact approval/provenance.

NODE-45 remains responsible for project-scale OCR/semantic/object/embedding indexing and search.

## Reference sets

An `IdentityReferenceSet` pins:

- `identity_id` and tenant/project/brand scope;
- identity type (`PRODUCT`, `LOGO`, `CHARACTER`, `FACE`, `STYLE_REFERENCE`);
- canonical asset ids;
- explicit reference asset versions/views;
- threshold calibration profile id/version;
- reference-set version.

Changing a canonical reference or calibration profile creates a new version; historical reports are never retroactively re-evaluated against the latest profile.

## Calibration, not arbitrary thresholds

P0 PRODUCT/LOGO profiles are produced from labeled positive, negative, and near-miss samples. The calibration algorithm evaluates candidate thresholds and records precision, recall, F1, false-positive/negative rates, ROC AUC, average precision and sample counts.

`REQUIRE_IDENTITY_SCORE` / `LOCK_IDENTITY` constraints may reference a profile but may not inject an ad-hoc numeric `threshold`. The deployed profile is pinned to:

- calibration dataset version;
- model/provider bundle version;
- preprocessor version;
- required signals and signal weights.

A model or preprocessor upgrade therefore requires a new calibrated profile/version before it can become the authoritative comparator.

The repository fixture in `fixtures/identity/node-44-calibration.json` is synthetic conformance data. It proves algorithm parity only; it must not be represented as a production-quality identity benchmark.

## Multi-signal evaluation

### Logo

The concrete structured provider supports deterministic exact SHA-256 and OCR/wordmark comparison directly. It also consumes versioned structured visual signals such as perceptual comparison and local feature matching from registered CV/VLM adapters.

A P0 Logo profile must require multiple independent signals. Correct OCR alone cannot make a stretched/recolored logo pass.

### Product

P0 Product profiles combine multiple signals such as:

- multimodal identity similarity;
- local shape/feature similarity;
- color/packaging similarity;
- detected brand/logo-region similarity.

No single embedding score is authoritative.

### Target region

When Design IR bounds exist, the caller should pass the target region. For whole-image inputs, a detector/analyzer must provide target-detection evidence or explicitly mark the whole artifact as the target. Missing target evidence is `IDENTITY_TARGET_REGION_UNAVAILABLE`, never silent whole-image fallback.

## Score and confidence

Each signal emits:

- score `0..100`;
- confidence `0..1`;
- evidence refs;
- optional reference view.

The calibration profile supplies weights, required signals, threshold, review floor and minimum confidence. A high similarity with low evidence confidence becomes `REVIEW`, not `PASS`.

Result states:

- `PASS` — calibrated score and confidence satisfy the profile;
- `REVIEW` — borderline score or insufficient confidence;
- `FAIL` — score below review floor;
- `UNAVAILABLE` — integration/provider boundary cannot produce a report.

## Fail-closed integration

NODE-39 already treats `LOCK_IDENTITY` and `REQUIRE_IDENTITY_SCORE` as fail-closed postflight types. The NODE-44 adapter throws for unavailable validation, stale references/profiles and numeric-threshold overrides, allowing NODE-39 to emit `VALIDATION_UNAVAILABLE` for HARD constraints.

Identity Engine does not duplicate the NODE-39 blocker.

## Artifact provenance

Every validation report records:

- identity/reference version;
- threshold profile/version;
- calibration dataset version;
- provider/version;
- preprocessor version;
- selected signal scores/confidence;
- evidence references;
- deterministic `identity_validation_snapshot_id`.

Multiple reports are combined into `identity-batch:<sha256>`. NODE-42 `ArtifactVersion` and provenance may pin this aggregate id. The stable export manifest includes it only when present, preserving legacy no-identity manifest hash behavior.

Raw embeddings and biometric templates are **not** written into Artifact history.

## Face privacy

FACE is not a default P0 path. Default policy disables face processing. When an explicit product feature enables it, the reference requires consent, purpose and retention metadata. Persistent biometric indexing and cross-tenant face indexes are prohibited by both the runtime policy and database schema in NODE-44.

Identity signals may not be repurposed for unrelated demographic or sensitive-attribute inference.

## Cache policy

Validation cache keys include:

- candidate checksum;
- identity/reference-set version;
- threshold profile/version;
- calibration dataset version;
- provider id/version;
- preprocessor version.

Changing any authoritative component invalidates the cache naturally.

## Persistence

`db/migrations/0003_identity_engine.sql` stores:

- logical profile ids + profile versions;
- labeled calibration samples;
- logical identity ids + reference-set versions;
- reference views/asset versions;
- identity validation reports and evidence;
- aggregate validation batches;
- ArtifactVersion/Provenance identity snapshot ids.

Logical ids and versions use composite tenant keys so `identity@v1` and `identity@v2` coexist without overwriting historical evidence.

## Production calibration requirement

Before a PRODUCT/LOGO profile is considered production-ready, build an approved benchmark per scenario with representative:

- same subject under supported lighting/view/background changes;
- distorted logo/recolor/warp near misses;
- wrong SKU/product family negatives;
- packaging text/logo changes;
- low-quality crops and detection failures;
- provider/model upgrade comparisons.

Select and review the operating threshold using precision/recall and business false-positive/false-negative cost. The synthetic repository fixture cannot satisfy this real-world acceptance requirement by itself.

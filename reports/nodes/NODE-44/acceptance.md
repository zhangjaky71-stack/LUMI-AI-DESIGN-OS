# NODE-44 Acceptance — Identity Engine

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-43-brand-rules-engine-release`

## Scope evidence

| Requirement | Evidence | Engineering status |
|---|---|---|
| Versioned Product/Logo reference sets | `types.ts`, `reference-set.ts`, `0003_identity_engine.sql` | Implemented |
| `create_reference_set` governed API | `reference-set.ts` | Implemented |
| Pairwise `compare(a,b,type)` API | `compare.ts` | Implemented |
| Canonical asset/view versions pinned | TS/Python contracts + composite DB FKs | Implemented |
| Multi-signal Logo validation | exact hash + OCR + structured perceptual/feature signals | Implemented |
| Multi-signal Product validation | multimodal/shape/color/brand-region profile contract | Implemented |
| No single embedding authority | Product/Logo profiles require >=2 required signals | Implemented |
| Scenario-specific calibrated thresholds | `calibration.ts`, `calibration.py` | Implemented |
| Positive/negative/near-miss dataset | shared synthetic conformance fixture | Implemented for conformance; real production dataset pending |
| Precision/recall/ROC/AP metrics | TS/Python calibration profile metrics | Implemented |
| No ad-hoc Constraint threshold override | `constraint-adapter.ts` | Implemented |
| Missing target fails closed | `IDENTITY_TARGET_REGION_UNAVAILABLE` | Implemented |
| Low-confidence crop requires review | runtime confidence floor + tests | Implemented |
| NODE-39 IdentitySimilarityValidator | `constraint-adapter.ts` | Implemented |
| HARD validator unavailable fail closed | adapter throws into existing NODE-39 postflight policy | Implemented |
| Artifact approval identity gate | `artifact-gate.ts` | Implemented |
| Exact identity snapshot provenance | Artifact SDK + Python Artifact history/export | Implemented |
| Tenant-bound snapshot/cache hashes | runtime/cache + tenant regression | Implemented |
| Legacy no-identity manifest hash preserved | conditional stable-manifest field + tests | Implemented |
| Version-aware cache key | `cache.ts` | Implemented |
| Face processing disabled by default | `privacy.ts`, Python policy | Implemented |
| No persistent/cross-tenant face index | runtime policy + DB CHECK | Implemented |
| Tenant/version persistence | `0003_identity_engine.sql` | Implemented |
| Artifact report/batch FK integrity | tenant-aware FK to `artifact_versions` | Implemented |
| TypeScript conformance tests | `packages/identity-engine/src/*.test.ts` | Implemented; hosted execution blocked before steps |
| Python conformance tests | `services/identity-engine/tests/test_identity_engine.py` | Implemented; hosted execution blocked before steps |
| Static contract validator | `scripts/validate_identity_engine.py` | Implemented; hosted execution blocked before steps |
| Product/Logo local benchmark | `scripts/benchmark_identity_engine.py` | Implemented; hosted measurement blocked before steps |
| Dedicated CI | `.github/workflows/identity-engine.yml` | Implemented; hosted runner blocked before steps |

## Frozen architecture assertions

1. Identity Engine does not create another Design IR mutation protocol.
2. Identity Engine does not create another hard-constraint blocker; NODE-39 remains authoritative.
3. Asset upload, scan, checksum/MIME verification and rights remain NODE-18 responsibilities.
4. Global OCR/semantic/embedding indexing and search remain NODE-45 responsibilities.
5. Product/Logo identity is never decided from one generic embedding score.
6. Numeric thresholds are calibration-profile data, not prompt or constraint literals.
7. Reference/profile/provider/preprocessor versions are preserved in every validation snapshot.
8. Snapshot/cache/report hashes bind `organization_id`; cross-tenant logical-id collisions cannot share validation cache/evidence ids.
9. Historical Artifact identity evidence is immutable and not reinterpreted by a newer model/profile.
10. Face processing is opt-in and purpose/retention constrained; no persistent or cross-tenant face index exists in NODE-44.
11. Raw embeddings/biometric templates are not placed into ArtifactVersion/provenance.

## Test cases implemented

- exact logo match;
- stretched/recolored logo near miss;
- same product under background change;
- wrong SKU/product negative;
- low-confidence crop -> REVIEW;
- missing target -> fail closed;
- required signal unavailable -> fail closed;
- stale reference asset version;
- cross-tenant candidate/reference rejection;
- threshold/profile/provider/preprocessor version mismatch;
- ad-hoc numeric threshold rejection;
- default face-processing denial;
- deterministic batch snapshot;
- tenant-bound cache/batch identity;
- cache invalidation on calibration/model version changes;
- governed reference-set publish;
- pairwise multi-signal compare;
- Artifact snapshot mismatch/approval failure;
- legacy no-identity Artifact hash compatibility.

## Calibration honesty

`fixtures/identity/node-44-calibration.json` is synthetic conformance data. It proves the calibration algorithm and TS/Python contract; it does **not** prove production thresholds. `reports/nodes/NODE-44/calibration.md` defines the real-data calibration gate.

## Hosted validation evidence

The first dedicated NODE-44 run was triggered from release head `bb21cb276f02d0e17da2932e59b98c1efa22be35`:

```text
workflow: Identity Engine
run_id: 31793702999
identity-contract job: 94746021396
identity-contract conclusion: failure
identity-contract runner_id: 0
identity-contract steps: []
identity-quality: skipped
identity-integration: skipped
identity-benchmark: skipped
```

GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

This is an **external GitHub Actions account/billing blocker**. The contract job received no runner and executed zero steps. Therefore no NODE-44 TypeScript typecheck/test, Python compile/test/Ruff/Pyright, integration suite, static validator, or benchmark actually ran on the hosted environment. This failure must not be interpreted as either a code failure or PASS.

Completion still requires all of these to **actually execute green** after the runner/account condition is resolved:

```text
identity-contract
identity-quality
identity-integration
identity-benchmark
```

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Next: NODE-45 Asset Intelligence after NODE-44 release evidence is recorded.

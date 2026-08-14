# NODE-44 Acceptance — Identity Engine

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-43-brand-rules-engine-release`

## Scope evidence

| Requirement | Evidence | Engineering status |
|---|---|---|
| Versioned Product/Logo reference sets | `packages/identity-engine/src/types.ts`, `db/migrations/0003_identity_engine.sql` | Implemented |
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
| Legacy no-identity manifest hash preserved | conditional stable-manifest field + tests | Implemented |
| Version-aware cache key | `cache.ts` | Implemented |
| Face processing disabled by default | `privacy.ts`, Python policy | Implemented |
| No persistent/cross-tenant face index | runtime policy + DB CHECK | Implemented |
| Tenant/version persistence | `0003_identity_engine.sql` | Implemented |
| TypeScript conformance tests | `packages/identity-engine/src/*.test.ts` | Implemented; hosted execution pending |
| Python conformance tests | `services/identity-engine/tests/test_identity_engine.py` | Implemented; hosted execution pending |
| Static contract validator | `scripts/validate_identity_engine.py` | Implemented; hosted execution pending |
| Product/Logo local benchmark | `scripts/benchmark_identity_engine.py` | Implemented; hosted measurement pending |
| Dedicated CI | `.github/workflows/identity-engine.yml` | To be published in this node |

## Frozen architecture assertions

1. Identity Engine does not create another Design IR mutation protocol.
2. Identity Engine does not create another hard-constraint blocker; NODE-39 remains authoritative.
3. Asset upload, scan, checksum/MIME verification and rights remain NODE-18 responsibilities.
4. Global OCR/semantic/embedding indexing and search remain NODE-45 responsibilities.
5. Product/Logo identity is never decided from one generic embedding score.
6. Numeric thresholds are calibration-profile data, not prompt or constraint literals.
7. Reference/profile/provider/preprocessor versions are preserved in every validation snapshot.
8. Historical Artifact identity evidence is immutable and not reinterpreted by a newer model/profile.
9. Face processing is opt-in and purpose/retention constrained; no persistent or cross-tenant face index exists in NODE-44.
10. Raw embeddings/biometric templates are not placed into ArtifactVersion/provenance.

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
- cache invalidation on version changes;
- Artifact snapshot mismatch/approval failure;
- legacy no-identity Artifact hash compatibility.

## Calibration honesty

`fixtures/identity/node-44-calibration.json` is synthetic conformance data. It proves the calibration algorithm and TS/Python contract; it does **not** prove production thresholds. `reports/nodes/NODE-44/calibration.md` defines the real-data calibration gate.

## Hosted validation

No hosted NODE-44 run is claimed until the release PR exists and GitHub Actions actually attempts the dedicated workflow.

Completion requires all of these to **actually execute green**:

```text
identity-contract
identity-quality
identity-integration
identity-benchmark
```

If GitHub Actions cannot start because of the account payment/spending-limit condition already observed on prior nodes, record the exact zero-step runner evidence as an **external CI blocker**. Do not mark the node PASS or COMPLETE.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Next: NODE-45 Asset Intelligence after NODE-44 release evidence is recorded.

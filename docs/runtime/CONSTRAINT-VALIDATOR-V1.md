# LUMI Constraint Validator Runtime V1

> Node: NODE-39  
> Contract source: NODE-14 Constraint Engine Specification V1  
> Mutation source: NODE-38 Design IR Runtime  
> Status: IMPLEMENTED / VALIDATING / not COMPLETE

## 1. Runtime boundary

The validator is a server-side enforcement boundary around Design IR mutations. It does **not** create a second document protocol and it does not mutate persisted IR directly.

```text
DesignDocument + DesignOperation(s)
        |
        v
resolve active constraint snapshot
        |
        v
simulate NODE-38 atomic transaction
        |
        v
preflight deterministic validators
        |
        +-- HARD violation/conflict/stale snapshot --> DENY, no candidate exposed
        |
        +-- SOFT/ADVISORY --> ALLOW_WITH_WARNINGS
        |
        +-- clean --> ALLOW
        v
persist candidate outside this package
        |
        v
render/generate
        |
        v
postflight plugin validators
        |
        +-- HARD --> FAIL
        +-- SOFT --> REPAIR
        +-- clean/advisory-only --> PASS
```

Prompt instructions are never the enforcement boundary.

## 2. Frozen constraint model

Every constraint has:

- stable `id`;
- V1 `type`;
- structured `scope`;
- `HARD | SOFT | ADVISORY` severity;
- source and numeric priority;
- structured `parameters`;
- active state;
- optional `document_version` snapshot guard.

JSON Schemas:

- `schemas/design-constraints/constraint.schema.json`
- `schemas/design-constraints/violation.schema.json`

The complete evaluator map is frozen in:

- `config/design-constraints/evaluator-coverage.v1.json`

## 3. Precedence and conflicts

Frozen source precedence:

```text
SAFETY_SYSTEM
> USER_EXPLICIT
> APPROVED_BRAND_RULE
> PROJECT_RULE
> RECIPE_RULE
> AGENT_INFERRED
> STYLE_PREFERENCE
```

Numeric `priority` only orders rules after source precedence. Two incompatible rules at the same source precedence, priority, type and scope create `CONSTRAINT_CONFLICT`; the resolver does not silently choose one.

A constraint pinned to a different `document_version` is stale. A stale HARD snapshot fails closed until the caller refreshes/re-resolves the rule set.

## 4. Deterministic preflight evaluators

The following rules are evaluated from Design IR without LLM/VLM calls:

- `LOCK_POSITION`
- `LOCK_SIZE`
- `LOCK_ROTATION`
- `LOCK_TRANSFORM`
- `LOCK_ASPECT_RATIO`
- `LOCK_LAYER_ORDER`
- `LOCK_PARENT`
- `LOCK_CONTENT`
- `LOCK_TEXT`
- `LOCK_ASSET`
- `LOCK_STYLE`
- `LOCK_BRAND` binding
- `MUST_STAY_INSIDE`
- `MUST_NOT_OVERLAP`
- `MIN_MARGIN`
- `SAFE_AREA`

`SAFE_AREA.region` is a normalized rectangle. It is converted through the bound frame before pixel-space containment is evaluated.

All geometry comparisons use an explicit tolerance profile rather than raw float equality.

## 5. Atomic operation enforcement

`guardedExecute` / `guarded_execute` first use NODE-38 `executeOperations` / `execute_operations` to create an immutable candidate. Constraints compare the original and candidate snapshots.

Consequences:

- BATCH semantics stay identical to NODE-38;
- generic `SET_PROPERTY` cannot bypass a lock;
- reparent/reorder is validated against the resulting graph;
- HARD failure exposes no candidate for persistence;
- the original document is not mutated.

## 6. Override security

Overrides are scoped to:

- exact `constraint_id`;
- exact `document_id`;
- exact `document_version`;
- actor;
- non-empty reason;
- optional expiration;
- optional one-time consumption.

`SAFETY_SYSTEM` constraints cannot be overridden by this user-level token mechanism. Expired, stale, mismatched or already-consumed tokens are invalid.

Audit persistence is external to this package; `consumeOverrideToken` / `consume_override_token` are pure lifecycle helpers.

## 7. Postflight plugin model

Postflight validation is adapter-based so NODE-39 does not hardcode model providers.

Implemented adapters/contracts:

- QR scannability;
- protected-region visual comparison;
- output resolution;
- structured contrast/readability;
- Brand Compliance delegation to NODE-43;
- Identity Similarity delegation to NODE-44.

For HARD postflight requirements, missing or crashing validators produce `VALIDATION_UNAVAILABLE` and fail closed. They never become PASS.

## 8. Real QR validation

Python provides `OpenCvQrDecoder`, backed by `cv2.QRCodeDetector`.

The validator checks:

- QR detected and decodable;
- payload equality when expected payload is frozen;
- target-size readability signal;
- quiet-zone warning when the decoder/adapter can report it.

The committed real fixture decodes to `https://lumi.example/qr` and its binary SHA-256 is pinned by the contract validator.

## 9. Protected region comparison

`OpenCvProtectedRegionComparator` uses a normalized crop and multiple signals:

- structural similarity signal;
- Canny edge difference;
- LAB mean color delta;
- optional future embedding similarity.

This avoids brittle byte/pixel equality. The Python tests specifically verify that high-quality JPEG recompression can pass while a substantive content/color edit fails.

## 10. Contrast/readability

`StructuredContrastEvaluator` calculates relative luminance and contrast ratio for explicit structured colors. `min_ratio` comes from the constraint profile.

Complex photographic/image backgrounds require a sampling/vision plugin. The runtime deliberately does not pretend a universal fixed threshold is valid for every artistic scene.

## 11. Constraint snapshot and Agent context

Both runtimes can produce a deterministic snapshot of:

- document id/version;
- effective constraints;
- conflicts;
- stale rule ids.

The snapshot is canonically SHA-256 hashed so ArtifactVersion/AgentRun can record the exact rule state that governed a decision.

A separate compact summary is provided for Agent planning. The Agent summary is context only; server-side validator enforcement remains authoritative.

## 12. Violation contract

Violations are machine-readable and localized later by `reason_code`. Typical fields:

```text
constraint_id
type
severity
target_id
validator
score/threshold
expected/actual
reason_code
repair_hint
raw_evidence_ref
```

Root-cause aggregation deduplicates repeated evidence while keeping the strongest severity.

## 13. Benchmark corpus

`fixtures/constraints/node-39-benchmark-spec.json` defines a deterministic 270-case corpus:

- 100 structure lock cases;
- 50 QR variants;
- 50 protected-region edits;
- 50 identity adapter cases;
- 20 compression false-positive cases.

NODE-44 owns calibrated Product/Logo identity scoring. NODE-39 only verifies identity adapter/fail-closed behavior.

`benchmark_constraint_validator.py` also measures a 2,000-node document with 100 operations and 100 constraints. NODE-39 records median/p95 but does not invent a hard latency SLO before machine calibration is available.

## 14. Validation commands

```bash
pnpm --filter @lumi/design-constraints typecheck
pnpm --filter @lumi/design-constraints test

PYTHONPATH=services/domain/src python scripts/validate_constraint_runtime.py
python scripts/build_constraint_benchmark_corpus.py --check
PYTHONPATH=services/domain/src python scripts/benchmark_constraint_validator.py

uv run pytest \
  services/domain/tests/test_constraint_validator.py \
  services/domain/tests/test_constraint_quality.py -q
```

Real image tests require `opencv-python-headless`; CI installs a pinned test adapter without changing the frozen workspace lock.

## 15. Non-goals / ownership handoff

NODE-39 does not implement:

- full Brand Rule extraction/compliance logic — NODE-43;
- calibrated product/logo identity models — NODE-44;
- Canvas rendering — NODE-40;
- Artifact approval/version persistence — Artifact/Version layer.

Those systems must integrate through the frozen constraint evaluator/adaptor contracts instead of bypassing or duplicating this validator.

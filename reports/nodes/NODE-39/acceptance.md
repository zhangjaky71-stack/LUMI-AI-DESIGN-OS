# NODE-39 — Constraint Validator Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-39-constraint-validator`  
> Base: `node-38-design-ir-runtime-release`

## Scope evidence

| Requirement | Evidence | State |
| --- | --- | --- |
| Reuse NODE-38 mutation boundary | `packages/design-constraints/src/engine.ts`, Python `guarded_execute` | IMPLEMENTED |
| Frozen NODE-14 Constraint Schema | `schemas/design-constraints/constraint.schema.json` | IMPLEMENTED |
| Frozen violation schema | `schemas/design-constraints/violation.schema.json` | IMPLEMENTED |
| All 24 V1 types have evaluator/adapter coverage | `config/design-constraints/evaluator-coverage.v1.json` | IMPLEMENTED |
| HARD/SOFT/ADVISORY decisions | aggregator + tests | IMPLEMENTED |
| Source precedence | `resolver.ts`, Python resolver | IMPLEMENTED |
| Equal-precedence conflict surfacing | resolver + tests | IMPLEMENTED |
| Stale snapshot fail-closed | resolver/engine + tests | IMPLEMENTED |
| Deterministic geometry/content preflight | `evaluators.ts`, Python mirror | IMPLEMENTED |
| Normalized SAFE_AREA semantics | TS/Python evaluators + parity tests | IMPLEMENTED |
| Batch atomicity | NODE-38 candidate simulation + tests | IMPLEMENTED |
| Scoped audited override | `override.ts`, Python mirror + tests | IMPLEMENTED |
| Constraint set canonical hash | `snapshot.ts`, Python snapshot hash + tests | IMPLEMENTED |
| Compact Agent constraint summary | snapshot APIs | IMPLEMENTED |
| QR postflight contract | `QrScannabilityEvaluator` | IMPLEMENTED |
| Real QR decoder | Python `OpenCvQrDecoder` + committed QR fixture | IMPLEMENTED |
| Protected-region multi-signal compare | `ProtectedRegionEvaluator`, `OpenCvProtectedRegionComparator` | IMPLEMENTED |
| Compression false-positive tolerance test | Python protected-region test | IMPLEMENTED |
| Structured contrast/readability | TS/Python `StructuredContrastEvaluator` | IMPLEMENTED |
| Resolution postflight | TS/Python `ResolutionEvaluator` | IMPLEMENTED |
| Brand adapter boundary | `DelegatingBrandEvaluator` | IMPLEMENTED; NODE-43 scoring pending by design |
| Identity adapter boundary | `DelegatingIdentityEvaluator` | IMPLEMENTED; NODE-44 scoring pending by design |
| Hard validator unavailable fail-closed | postflight runtime + tests | IMPLEMENTED |
| 270-case benchmark corpus | benchmark spec + deterministic builder | IMPLEMENTED |
| 2k node / 100 op / 100 constraint benchmark | `scripts/benchmark_constraint_validator.py` | IMPLEMENTED; hosted measurement pending |
| Static contract validator | `scripts/validate_constraint_runtime.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/constraint-validator.yml` | IMPLEMENTED; hosted runner blocked externally |

## Frozen V1 type coverage

### Deterministic preflight

- LOCK_POSITION
- LOCK_SIZE
- LOCK_ROTATION
- LOCK_TRANSFORM
- LOCK_ASPECT_RATIO
- LOCK_LAYER_ORDER
- LOCK_PARENT
- LOCK_CONTENT
- LOCK_TEXT
- LOCK_ASSET
- LOCK_STYLE
- LOCK_BRAND binding
- MUST_STAY_INSIDE
- MUST_NOT_OVERLAP
- MIN_MARGIN
- SAFE_AREA

### Postflight / plugin-backed

- PROTECT_REGION
- REQUIRE_SCANNABILITY
- REQUIRE_CONTRAST
- REQUIRE_TEXT_READABILITY
- REQUIRE_RESOLUTION
- LOCK_IDENTITY → NODE-44 adapter
- REQUIRE_IDENTITY_SCORE → NODE-44 adapter
- REQUIRE_BRAND_COMPLIANCE → NODE-43 adapter
- LOCK_BRAND visual compliance → NODE-43 adapter

## Safety / failure policy

- No LLM/VLM is used for deterministic IR geometry or content locks.
- HARD violations never expose a persistence candidate.
- Missing/crashing HARD postflight validators return `VALIDATION_UNAVAILABLE` and FAIL.
- SAFETY_SYSTEM constraints are not user-overridable.
- Stale override/document versions are rejected.
- Same-precedence incompatible rules become explicit conflicts.
- QR validation uses a real decoder in the Python hosted quality gate.
- Protected-region comparison tolerates encoded-image noise through multi-signal thresholds rather than exact byte equality.

## Benchmark corpus

The deterministic corpus contains 270 cases:

- 100 structure-lock cases;
- 50 QR variants;
- 50 protected-region edits;
- 50 identity adapter cases;
- 20 compression false-positive cases.

The performance harness measures 2,000 nodes / 100 operations / 100 constraints and reports median/p95. No unmeasured latency result is claimed in this report.

## Hosted CI attempt

Draft PR #39 triggered Constraint Validator workflow run `31783395060` for release head `19a531899a31e020403e8d8b468296ea7c7a6df4`.

Observed jobs:

- `constraint-contract`: **failure before execution**;
- `constraint-quality`: skipped because the contract dependency did not run green;
- `constraint-benchmark`: skipped because the quality dependency did not run green.

The contract job contained no executed steps. GitHub check annotation reported:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

This is an external GitHub Actions account/billing blocker. It is **not** evidence of a NODE-39 implementation or test failure.

## Acceptance gates before COMPLETE

1. Hosted `constraint-contract` executes green.
2. Hosted `constraint-quality` executes TS tests/typecheck and Python pytest/Ruff/Pyright green.
3. Real OpenCV QR and protected-region tests execute green in hosted CI.
4. `constraint-benchmark` executes and records the benchmark result.
5. No contract drift against NODE-14 or mutation drift against NODE-38.
6. Release PR remains stack-compatible with `node-38-design-ir-runtime-release`.

## Current disposition

NODE-39 remains **IMPLEMENTED / VALIDATING / not COMPLETE**. Implementation, schemas, fixtures, tests, benchmark harness, runtime documentation and CI definitions are present, but hosted validation has not executed due the external GitHub billing/spending-limit condition. The node must not be marked COMPLETE until the required hosted jobs actually run green.

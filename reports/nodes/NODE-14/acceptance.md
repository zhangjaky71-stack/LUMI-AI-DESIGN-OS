# NODE-14 Acceptance Report — Constraint Engine V1

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Branch: `node-14-constraint-engine`  
> Official node: **NODE-14 — Constraint Engine Specification V1**  
> Base: `node-13-design-ir`

## 1. Acceptance intent

NODE-14 converts design protections from prompt prose into machine-enforceable server-side policy over NODE-13 Design IR operations and structured postflight evidence.

The implementation does not treat Agent prompt compliance as enforcement.

## 2. Contract artifacts

```text
contracts/constraints/v1/
├── manifest.json
├── evaluator-registry.json
├── constraint.schema.json
├── violation.schema.json
├── override.schema.json
└── evidence.schema.json
```

All schemas use JSON Schema Draft 2020-12.

## 3. Frozen V1 vocabulary

Exactly **24** constraint types are registered.

### Geometry — 7

```text
LOCK_POSITION
LOCK_SIZE
LOCK_ROTATION
LOCK_TRANSFORM
LOCK_ASPECT_RATIO
LOCK_LAYER_ORDER
LOCK_PARENT
```

### Content / identity — 6

```text
LOCK_CONTENT
LOCK_TEXT
LOCK_ASSET
LOCK_IDENTITY
LOCK_STYLE
LOCK_BRAND
```

### Region — 5

```text
PROTECT_REGION
MUST_STAY_INSIDE
MUST_NOT_OVERLAP
MIN_MARGIN
SAFE_AREA
```

### Quality — 6

```text
REQUIRE_CONTRAST
REQUIRE_SCANNABILITY
REQUIRE_TEXT_READABILITY
REQUIRE_BRAND_COMPLIANCE
REQUIRE_RESOLUTION
REQUIRE_IDENTITY_SCORE
```

Every type owns an evaluator phase/contract in `evaluator-registry.json`.

## 4. Severity and precedence

Frozen severities:

```text
HARD
SOFT
ADVISORY
```

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

Reference runtime uses source precedence before local priority.

Same type/scope/source-priority level with incompatible parameters generates explicit `CONSTRAINT_PRECEDENCE_CONFLICT` instead of silent last-write-wins behavior.

## 5. Preflight implementation

`preflight()`:

1. detects same-level rule conflicts;
2. uses NODE-13 `apply_operation()` to build a deep candidate Design IR;
3. turns stale/invalid Design IR operations into non-overridable `CONSTRAINT_OPERATION_INVALID`;
4. computes before/after semantic changes;
5. resolves active effective constraints;
6. evaluates geometry/content/region policy;
7. returns `ALLOW`, `ALLOW_WITH_WARNINGS` or `DENY`.

Candidate construction never mutates the source document.

## 6. Semantic change detection

Reference preflight identifies:

```text
existence
position
size
rotation
transform
parent
layer_order
content
text
asset
style
brand
```

This allows BATCH and indirect property mutations to be evaluated against final candidate state rather than operation-name heuristics.

## 7. Implemented preflight evaluators

Reference behavior includes:

- property/transform locks;
- aspect-ratio preservation with tolerance;
- parent/layer lock checks;
- missing strict target rejection;
- role/node/frame scope resolution;
- protected region blocking;
- must-stay-inside / safe-area containment;
- minimum margin;
- must-not-overlap;
- soft/advisory warning path;
- BATCH final-candidate policy atomicity.

## 8. Structured USER_EXPLICIT protection

`compile_user_explicit_protections()` accepts structured protection intent and emits HARD `USER_EXPLICIT` constraints.

Supported protection keys include:

```text
position
size
rotation
transform
content
text
asset
identity
style
brand
scannability
```

Natural-language parsing is deliberately not part of the enforcement function.

## 9. Postflight evidence contract

Implemented evidence kinds:

```text
content_identity
text_match
identity
brand_compliance
protected_region_diff
contrast
qr
text_readability
resolution
```

An active HARD postflight constraint with missing evidence fails. “Not validated” is never interpreted as PASS.

## 10. QR enforcement

`REQUIRE_SCANNABILITY` core PASS requires:

```text
detected = true
decoded = true
payload_match = true
```

Core failure emits `CONSTRAINT_QR_NOT_SCANNABLE`.

Quiet-zone/size quality issues can produce `CONSTRAINT_QR_QUIET_ZONE_WARNING` when decode and payload identity still pass.

## 11. Quality/postflight behavior

Implemented contract interpretation for:

- contrast ratio;
- text readability score;
- brand compliance score;
- identity score;
- width/height resolution;
- protected-region diff ratio;
- QR evidence.

Outcomes:

```text
PASS
FAIL_REPAIRABLE
FAIL_HARD
```

Only explicitly repairable non-safety HARD failures can produce `FAIL_REPAIRABLE`.

## 12. Override audit

`create_override_audit()` requires:

```text
override_id
actor_id
non-empty reason
authorized=true
```

Safety/system and `NEVER` constraints cannot be overridden.

The original constraint is preserved; override is separate audit evidence.

## 13. Constraint snapshot hash

`constraint_snapshot_hash()` produces deterministic SHA-256 over the effective constraint set.

Input ordering does not affect the snapshot. This becomes the explanation/provenance link for later ArtifactVersion storage.

## 14. Tests implemented

`services/constraint-engine/tests/test_constraint_engine.py` covers:

- geometry lock denial;
- proportional vs distorted logo resize;
- user-explicit vs agent-inferred precedence;
- same-level HARD conflict;
- BATCH hard violation denial without source mutation;
- SOFT style warning;
- QR success/warning/failure;
- missing protected-region evidence;
- excessive protected-region diff;
- authorized override audit;
- SAFETY_SYSTEM override denial;
- stale document-version denial;
- missing target denial;
- structured explicit protection compiler;
- deterministic snapshot hash.

## 15. 100-case executable benchmark

Benchmark matrix:

`benchmarks/constraint-engine/v1/matrix.json`

10 templates × 10 deterministic variants = **100 cases**:

1. only-background
2. keep-product
3. resize-logo-proportionally
4. keep-logo
5. keep-qr
6. change-title-size
7. safe-area
8. non-overlap
9. soft-style-warning
10. qr-postflight

`scripts/run_constraint_benchmark.py` expands the matrix, runs every case through the real reference engine and checks expected decisions/outcomes/message codes.

It also asserts exactly 100 unique case IDs and 10 cases per template.

## 16. Contract validator

`scripts/validate_constraint_contracts.py` verifies:

- exactly 24 V1 types;
- no duplicates;
- frozen severity/source lists;
- strictly descending source precedence;
- evaluator registry covers every type;
- postflight/BOTH evaluators declare evidence kinds;
- schema dialect/IDs;
- schema enums match manifest;
- stable `CONSTRAINT_*` message-code policy;
- violation contract contains no localized free-form UI message field;
- evidence registry consistency;
- reference engine forbidden-import boundary.

## 17. Independent CI gate

`.github/workflows/constraint-contract.yml` runs:

```text
Python 3.12 compileall
NODE-13 Design IR contract revalidation
NODE-14 contract validator
Constraint reference unittests
100-case executable benchmark
```

It intentionally does not depend on the stale upstream `uv.lock`.

## 18. Security / trust boundary

Reference Constraint Engine may depend only on stdlib, itself and `lumi_design_ir`.

It is statically forbidden from importing transport, persistence, LangGraph, provider SDK, HTTP client or broker implementation packages.

Prompt/Agent output cannot bypass server-side validation.

## 19. Current external blocker

GitHub hosted Actions cannot currently start because account payment/Actions spending requires attention. The previously retrieved GitHub annotation states:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings.

No real CI PASS is claimed while jobs fail before checkout with no runner/steps.

## 20. Acceptance checklist

- [x] Constraint JSON Schema published.
- [x] Violation schema published.
- [x] Override audit schema published.
- [x] Postflight evidence schema published.
- [x] exactly 24 V1 types frozen.
- [x] all V1 types have evaluator contracts.
- [x] HARD/SOFT/ADVISORY frozen.
- [x] source precedence frozen.
- [x] same-level conflicts explicit.
- [x] preflight candidate enforcement implemented.
- [x] postflight evidence enforcement implemented.
- [x] USER_EXPLICIT structured protections implemented.
- [x] BATCH hard-violation policy atomicity implemented.
- [x] QR evidence contract implemented.
- [x] protected-region evidence interpretation implemented.
- [x] override audit implemented.
- [x] safety override rejection implemented.
- [x] deterministic constraint snapshot hash implemented.
- [x] 100 logical benchmark cases implemented and executable.
- [x] dependency-light independent CI gate committed.
- [ ] real hosted-runner Constraint Contract workflow PASS.

## 21. Completion gate

After external Actions recovery:

1. real Python 3.12 runner starts;
2. compileall PASS;
3. NODE-13 revalidation PASS;
4. Constraint contract validator PASS;
5. Constraint Engine unittest PASS;
6. 100-case benchmark PASS;
7. evidence is recorded;
8. only then mark NODE-14 COMPLETE.

Next official node: **NODE-15 — Artifact / Version / Provenance**.

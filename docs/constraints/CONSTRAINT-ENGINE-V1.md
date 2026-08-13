# LUMI Constraint Engine V1

> Contract status: **FROZEN FOR NODE-14 IMPLEMENTATION / VALIDATING**  
> Schema version: `1.0`  
> Depends on: **NODE-13 Design IR V1**

## 1. Purpose

Constraint Engine converts design requirements such as:

```text
二维码不要动
产品保持不变
Logo 不能拉伸
只改背景
二维码最终必须可扫
```

from prompt prose into server-side machine-enforceable policy.

The enforcement path is:

```text
structured user/brand/project rule
-> Constraint V1
-> candidate DesignOperation
-> NODE-13 candidate Design IR
-> preflight
-> generation/render/edit
-> structured validator evidence
-> postflight
-> version/approval gate
```

**Prompt text is not an enforcement boundary.** Agent planning may receive a compact summary, but the server-side engine decides whether an operation/version is allowed.

## 2. Canonical contract files

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

## 3. Severity

```text
HARD      default cannot be violated; blocks the operation/version
SOFT      permits the operation but emits a warning/penalty
ADVISORY  design guidance; never a hard enforcement decision by itself
```

A HARD rule is not automatically user-overridable. Safety/system constraints are never overridden by normal product users.

## 4. Source precedence

Frozen precedence, highest first:

```text
SAFETY_SYSTEM        700
USER_EXPLICIT        600
APPROVED_BRAND_RULE  500
PROJECT_RULE         400
RECIPE_RULE          300
AGENT_INFERRED       200
STYLE_PREFERENCE     100
```

Source precedence dominates local numeric `priority`.

For the same constraint type and same scope:

- a higher source precedence wins;
- within one source precedence, higher `priority` wins;
- same source/priority/scope with incompatible parameters is an explicit conflict;
- conflict is never silently resolved by array/database order.

A same-level HARD conflict produces `CONSTRAINT_PRECEDENCE_CONFLICT` and preflight DENY.

## 5. Constraint types — exactly 24

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

Unknown constraint types are not silently interpreted under V1.

## 6. Scope

A rule can select targets with:

```text
node_ids
semantic roles
frame_ids
normalized/absolute region
```

Explicit node/frame IDs are strict references. If an active HARD rule names a missing target, preflight returns `CONSTRAINT_TARGET_MISSING`; silently dropping an old protection rule would be unsafe.

Role selectors resolve against NODE-13 semantic roles at evaluation time.

## 7. Preflight

Preflight never mutates the source Design IR.

```text
validate precedence/conflicts
-> apply NODE-13 operation to deep candidate
-> reject stale/invalid operation
-> semantic before/after diff
-> evaluate active constraints
-> ALLOW | ALLOW_WITH_WARNINGS | DENY
```

The reference engine compares the resulting candidate document rather than merely matching operation names. This matters for BATCH and indirect property changes.

Semantic change dimensions include:

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

## 8. Structural failure in preflight

A stale `expected_document_version`, invalid reparent, missing resource or other NODE-13 failure becomes a non-overridable synthetic HARD violation:

```text
CONSTRAINT_OPERATION_INVALID
```

Constraint Engine therefore never returns ALLOW for a structurally invalid Design IR candidate.

## 9. Geometry locks

`LOCK_POSITION`, `LOCK_SIZE`, `LOCK_ROTATION` and `LOCK_TRANSFORM` compare before/after geometry.

`LOCK_ASPECT_RATIO` permits proportional resize within a configurable tolerance and denies distortion.

`LOCK_LAYER_ORDER` protects sibling ordering; `LOCK_PARENT` protects hierarchy.

## 10. Region constraints

V1 reference evaluators support:

- containment in an allowed region;
- normalized region relative to target parent;
- minimum margin by shrinking the allowed rectangle;
- no-overlap against named nodes;
- protected-region change blocking.

The reference engine uses candidate NODE-13 transform geometry consistently. A production world-bounds derivation for nested transform composition belongs to NODE-38 Design IR Runtime and must preserve these contract outcomes.

## 11. User-explicit protection compiler

`compile_user_explicit_protections()` accepts a **structured intent-parser result**, not raw prose.

Example structured request:

```text
target = qr
protections = [transform, content, scannability]
```

produces:

```text
LOCK_TRANSFORM (HARD / USER_EXPLICIT)
LOCK_CONTENT (HARD / USER_EXPLICIT)
REQUIRE_SCANNABILITY (HARD / USER_EXPLICIT)
```

Natural-language interpretation may happen in an Agent/intent parser, but enforcement only begins after structured constraints exist.

## 12. BATCH atomicity

NODE-13 already guarantees structural BATCH atomicity. NODE-14 adds policy atomicity:

```text
build one candidate for complete BATCH
-> evaluate all active constraints against final candidate
-> any HARD violation => DENY the entire batch
```

There is no partial write such as “background changed but protected QR accidentally moved.”

## 13. Preflight result

```text
ALLOW
ALLOW_WITH_WARNINGS
DENY
```

Result contains:

```text
candidate_document / candidate_document_version when structurally valid
hard violations
warnings
```

A denied candidate is never permission to persist an approved DesignDocument/ArtifactVersion.

## 14. Postflight is evidence-driven

Generative image/video/edit operations cannot be protected only by preflight. Postflight consumes **structured validator evidence**.

Evidence kinds V1:

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

Model/provider self-description is not evidence by itself.

**Missing evidence for an active HARD postflight constraint is a failure, not a pass.**

## 15. QR scannability

For `REQUIRE_SCANNABILITY`, core PASS requires at least:

```text
detected = true
decoded = true
payload_match = true
```

A core failure blocks HARD approval/export. `quiet_zone_ok=false` or `size_ok=false` can be emitted as a warning when the QR still decodes and payload matches.

QR payload comparison should use trusted expected payload/hash, not OCR/model guesswork.

## 16. Protected-region postflight

`PROTECT_REGION` postflight consumes a visual-diff evidence result with `diff_ratio` and a configured `max_diff`.

It deliberately does not require exact pixel equality: anti-aliasing, encoding and renderer differences may produce harmless pixel noise.

The actual image-diff/feature validator belongs to later visual/runtime Nodes; NODE-14 freezes how its evidence is interpreted.

## 17. Quality thresholds

V1 interprets structured evidence for:

```text
contrast ratio
text readability score
brand compliance score
identity score
output width/height
```

Threshold values live in each Constraint `parameters`, so the evaluator contract remains stable while a project/brand may choose stricter requirements.

## 18. Postflight result

```text
PASS
FAIL_REPAIRABLE
FAIL_HARD
```

Rules:

- no HARD failures => PASS, possibly with warnings;
- all HARD failures are explicitly repairable and none are SAFETY_SYSTEM => FAIL_REPAIRABLE;
- otherwise => FAIL_HARD.

This distinction feeds later bounded Auto Repair and approval logic. It does not itself perform repair.

## 19. Violation contract

Violation contains structured fields only:

```text
constraint_id
type
severity
phase
target_id
expected
actual
message_code
repair_hint
overrideable
```

`message_code` follows `CONSTRAINT_[A-Z0-9_]+`.

Validators do not compose localized user-interface prose. Web/Admin map message codes to human-language copy.

## 20. Override

Override requires:

```text
override_id
constraint_id
actor_id
non-empty reason
occurred_at
authorized = true
```

`SAFETY_SYSTEM` and `override_policy=NEVER` constraints reject override creation.

A valid override is version/audit evidence; it is not represented by deleting or disabling the original rule.

NODE-16 owns authorization policy; NODE-65 owns durable governance/audit retention.

## 21. Constraint snapshot hash

Every version-producing workflow can compute a deterministic SHA-256 of the effective constraint set.

Snapshot includes:

```text
rule identity/type/scope
severity/source/source precedence/priority
parameters
override policy
```

Input order does not change the hash.

NODE-15/42 persist this hash with ArtifactVersion/Provenance so the system can later explain what rule set was active when a version was generated or rejected.

## 22. Benchmark — 100 logical cases

`benchmarks/constraint-engine/v1/matrix.json` defines 10 high-value design-edit templates with 10 deterministic variants each:

```text
only-background
keep-product
resize-logo-proportionally
keep-logo
keep-qr
change-title-size
safe-area
non-overlap
soft-style-warning
qr-postflight
```

`scripts/run_constraint_benchmark.py` expands and executes exactly 100 unique cases against real NODE-13 fixtures and the reference Constraint Engine.

The benchmark validates behavior; it is not a static list whose only assertion is row count.

## 23. Independent validation

`.github/workflows/constraint-contract.yml` runs without `uv.lock`:

```text
Python 3.12 compileall
NODE-13 contract revalidation
Constraint schema/registry/dependency validator
Constraint reference unittest
100-case executable benchmark
```

The Constraint package may import the stdlib, itself and `lumi_design_ir`; it may not import FastAPI, SQLAlchemy, LangGraph, provider SDKs, broker clients or infrastructure frameworks.

## 24. Explicit non-ownership

NODE-14 does not own:

- natural-language intent model quality;
- database persistence of rules;
- RBAC authorization implementation;
- image-diff/OCR/QR/identity model implementation;
- Artifact approval/version persistence;
- repair loops;
- renderer world-transform optimization.

Those later Nodes must implement adapters that satisfy this frozen contract.

# LUMI Constraint Engine V1

Status: **FROZEN CONTRACT / NODE-14**  
Depends on: NODE-09 Domain Model, NODE-13 Design IR V1

## Purpose

Constraint Engine V1 turns explicit design restrictions into deterministic, machine-enforced contracts. Prompts may propose intent, but prompts are never the enforcement boundary. Server-side preflight prevents illegal Design Operations; postflight evaluates adapter-supplied visual observations after generative edits or rendering.

## Frozen precedence

Highest precedence wins for the same constraint type and scope:

1. `SAFETY_SYSTEM`
2. `USER_EXPLICIT`
3. `APPROVED_BRAND_RULE`
4. `PROJECT_RULE`
5. `RECIPE_RULE`
6. `AGENT_INFERRED`
7. `STYLE_PREFERENCE`

Within the winning source, larger `priority` wins. If multiple winners have the same source and priority but incompatible parameters, the engine returns `CONSTRAINT_SAME_LEVEL_CONFLICT`; it never silently chooses one.

## Severity

- `HARD`: violation denies deterministic preflight or blocks approval at postflight.
- `SOFT`: allowed with warning / repairable failure.
- `ADVISORY`: non-blocking design guidance.

## Constraint types

Geometry: `LOCK_POSITION`, `LOCK_SIZE`, `LOCK_ROTATION`, `LOCK_TRANSFORM`, `LOCK_ASPECT_RATIO`, `LOCK_LAYER_ORDER`, `LOCK_PARENT`.

Content / identity: `LOCK_CONTENT`, `LOCK_TEXT`, `LOCK_ASSET`, `LOCK_IDENTITY`, `LOCK_STYLE`, `LOCK_BRAND`.

Region: `PROTECT_REGION`, `MUST_STAY_INSIDE`, `MUST_NOT_OVERLAP`, `MIN_MARGIN`, `SAFE_AREA`.

Quality: `REQUIRE_CONTRAST`, `REQUIRE_SCANNABILITY`, `REQUIRE_TEXT_READABILITY`, `REQUIRE_BRAND_COMPLIANCE`, `REQUIRE_RESOLUTION`, `REQUIRE_IDENTITY_SCORE`.

Every type has an entry in `EVALUATOR_CONTRACTS`; no V1 type is a documentation-only placeholder.

## Preflight

Input is immutable `DesignIRDocument`, typed `DesignOperationBatch`, active `ConstraintSet`, and policy-authorized override records.

Output is exactly one of:

- `ALLOW`
- `ALLOW_WITH_WARNINGS`
- `DENY`

The engine fails closed on stale document revision, wrong document identity, missing target, same-level rule conflict, or any HARD lock violation. `apply_batch_with_constraints()` evaluates the full batch first; a denied batch never calls the Design IR mutation engine, preserving all-or-nothing semantics.

## Postflight

NODE-14 deliberately does not import OCR, QR, image-processing, provider, queue, ORM, or storage SDKs. Runtime adapters later provide typed `PostflightObservation` records. This keeps policy deterministic and testable while allowing NODE-39 and provider-specific runtimes to own actual visual measurement.

Mandatory quality examples:

- QR: detected, decoded, payload matches. Quiet-zone/module-size defects are warnings when decoding still succeeds.
- protected region: perceptual/feature difference score under configured threshold; exact pixel equality is not required.
- identity: measured score at or above configured threshold.
- contrast/readability/resolution/brand: measured adapter values evaluated against frozen parameters.

Missing observation for an active postflight constraint is a failure, not implicit success.

## Overrides

An override is an immutable audit record with actor, reason, time and external authorization `policy_decision_id`. `SAFETY_SYSTEM` constraints cannot be bypassed by an ordinary override record. Authorization itself belongs to the later access-policy/runtime layer; the Constraint Engine consumes only already-authorized override evidence.

## Snapshot hash

`constraint_snapshot_hash()` canonicalizes active constraints by constraint id and computes SHA-256. Artifact/Version work in NODE-15 can persist this hash so a decision can be explained against the exact rules active at that time.

## Explicit user locks

`structure_explicit_user_locks()` is intentionally conservative. It structures explicit lock language such as “二维码和产品都不要动” for known node targets; it does not infer hidden intent. QR targets receive transform/content locks plus scannability; logo/product targets receive transform + identity locks.

## Machine-readable artifacts

`tools/node14/export_constraint_schemas.py` emits:

- `constraint-set-v1.schema.json`
- `constraint-violation-v1.schema.json`
- `postflight-observation-v1.schema.json`
- `preflight-result-v1.schema.json`

## Benchmark

`benchmarks/constraints/constraint-following-v1.jsonl` contains 100 deterministic contract cases spanning only-background, product/logo/QR preservation, title-size edits, frame resize, soft style, QR, identity and protected-region behaviors. It is a contract benchmark; visual-runtime measurements are supplied by later adapters.

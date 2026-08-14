# NODE-50 — Visual Critic & Design Quality Engine

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / QUALITY CORE  
> Depends on: NODE-39, NODE-43, NODE-44, NODE-22, NODE-05  
> Produces: 多信号 Visual QA、设计评分、结构化 Critique、Quality Gate、typed Repair Plan  
> Runtime: `packages/quality-engine`  
> DB: `db/migrations/0009_visual_critic.sql`  
> CI: `.github/workflows/visual-critic.yml`

---

## 1. 目标

在生成后自动判断“是否达标、哪里有问题、是否可修复”，并且阻止同一生成器自我批准。Visual Critic 聚合 deterministic rules、NODE-39 Constraint、NODE-43 Brand、NODE-44 Identity、OCR/QR 和独立视觉 grader。

NODE-50 **只评估，不修改设计**。任何 repair action 都是 NODE-38 `DesignOperation` proposal；执行、预算、迭代、rollback 属于 NODE-51 Auto Repair。

## 2. 实施架构

```text
Exact ArtifactVersion + Exact DesignVersion
            ↓
      CriticSubject
            ↓
Deterministic Design IR / metadata graders
            ↓
NODE-39 Constraint PostflightReport
            ↓
NODE-43 BrandComplianceReport
            ↓
NODE-44 IdentityValidationReport
            ↓
OCR / QR programmatic graders
            ↓
Independent calibrated visual grader
            ↓
Hard gate + confidence gate + profile weighting
            ↓
QualityResult
 ├─ dimensions/evidence/violations
 ├─ DesignOperation repair_actions
 ├─ grader/calibration versions
 └─ PASS / WARN / REPAIR / HARD / REVIEW
            ↓
QualityResultRepository + Artifact quality_score summary
```

## 3. Ownership boundaries

### NODE-50 owns

- QualityProfile orchestration；
- multi-signal aggregation；
- score/confidence/status；
- independent critic isolation；
- calibration version validation；
- structured QualityResult；
- typed repair proposals；
- quality DB records and safe telemetry projection。

### NODE-50 does not own

- hard constraint truth → NODE-39；
- brand truth → NODE-43；
- product/logo identity truth → NODE-44；
- model provider SDK/routing → NODE-22；
- Design IR mutation → NODE-38/NODE-51；
- repair loop/budget/rollback → NODE-51；
- approval policy → later workflow/policy node。

## 4. Quality dimensions

Runtime freezes 13 dimensions:

```text
CONSTRAINT_COMPLIANCE
COMPOSITION
VISUAL_HIERARCHY
ALIGNMENT_SPACING
TYPOGRAPHY_READABILITY
CONTRAST
BRAND_CONSISTENCY
IDENTITY_CONSISTENCY
TEXT_ACCURACY
LOGO_INTEGRITY
QR_READABILITY
IMAGE_DEFECTS
RESOLUTION_EXPORT_READINESS
```

Each active dimension returns:

```text
score 0..100
confidence 0..1
threshold
weight
severity
hard_gate
passed
evidence_ids
reason_codes
```

## 5. Deterministic-first grading

`packages/quality-engine/src/deterministic.ts` implements programmatic checks before subjective grading:

- text box overflow from exact layout/measurement metadata；
- child outside parent bounds；
- deterministic hex-color contrast；
- expected Design IR text presence；
- minimum export resolution。

Known safe repairs produce current-version DesignOperations such as:

```text
RESIZE_NODE
MOVE_NODE
SET_TEXT
```

The critic never executes them.

## 6. Authoritative external signals

Typed ports consume existing domain reports rather than copying their logic:

```text
ConstraintQualityPort -> PostflightReport
BrandQualityPort      -> BrandComplianceReport
IdentityQualityPort   -> IdentityValidationReport[]
OcrQualityPort        -> normalized OCR result
QrQualityPort         -> decode/payload/target-size result
VisualGraderPort      -> calibrated VisualGradeResult
```

A hard QR/brand/identity/constraint failure remains hard even if aesthetic scores are high.

## 7. Visual grader isolation

Visual grader contract requires:

```text
role_id = visual-critic
grader_id
grader_version
model_provider/model_name/model_version
prompt_version
calibration_dataset_version
```

Rules:

1. Quality Engine contains no provider SDK imports.
2. Production adapters must use NODE-22 Model Gateway.
3. Same generation model + same critic prompt cannot self-approve; result routes to REVIEW.
4. Uncalibrated grader/version/dataset is unavailable, never silently accepted.
5. Timeout/failure routes to REVIEW when the active profile depends on that evidence.

## 8. Calibration

`fixtures/quality/node-50-calibration.json` is explicitly marked `SYNTHETIC_HUMAN_LABEL_STRUCTURE`.

It exists to test:

- threshold math；
- precision/recall/F1；
- FP/FN；
- version binding；
- minimum sample count；
- approval guardrails。

It is **not** evidence that a production VLM has completed human validation. A real production grader requires a blinded human-labeled dataset, inter-rater agreement and a new versioned calibration record.

## 9. Quality profiles

Implemented profiles:

```text
exploration
production-web
brand-strict
product-strict
print
social-fast
```

Profiles activate only applicable dimensions. Missing evidence on an active high-impact dimension does not become a fake PASS; low confidence enters `REVIEW_REQUIRED`.

Brand/identity/QR are not globally required for designs where the selected profile does not activate them.

## 10. Gate status

```text
FAIL_HARD
  any hard signal/violation

REVIEW_REQUIRED
  active hard-gate evidence below confidence floor
  or overall active evidence confidence below profile floor

PASS
  score >= pass threshold and no violations

PASS_WITH_WARNINGS
  score >= warning threshold but non-hard issues remain

FAIL_REPAIRABLE
  below warning threshold and typed repair actions exist

REVIEW_REQUIRED
  otherwise
```

Hard status is computed before score-based approval.

## 11. Structured repair plan

`repair_actions` is `DesignOperation[]` using the frozen NODE-38 operation set. The runtime removes stale-version operations and semantic duplicates.

No free-form repair prose is treated as executable.

## 12. Artifact persistence

`ArtifactEngineQualityAdapter`:

1. verifies exact organization/project/artifact/version/design-version identity；
2. writes full QualityResult to `QualityResultRepository`；
3. writes only normalized `overall_score / 100` into historical ArtifactVersion `quality_score`；
4. leaves content hash/status/branch head unchanged。

The DB migration mirrors this normalization with a trigger.

## 13. Database

`0009_visual_critic.sql` adds:

```text
quality_profiles
quality_grader_calibrations
quality_results
quality_dimension_results
quality_violations
quality_evidence
```

QualityResult is append-only evidence. Dimension/evidence/violation rows reference the exact result. Artifact summary score uses the existing 0–1 scale.

## 14. Observability

`qualityMetricSnapshot()` exports safe telemetry only:

- profile/version/status；
- score/confidence；
- hard violation count；
- repair count；
- unavailable grader count；
- evidence/dimension counts。

It does not expose prompt text, OCR text, image URLs or raw VLM responses.

LangSmith may link traces/experiments, but LUMI DB remains the source of truth for QualityResult.

## 15. NODE-05 release gate

Added:

```text
evals/datasets/visual-critic/suite.json
evals/datasets/visual-critic/v1/cases.json
evals/fixtures/visual-critic/baseline.json
evals/fixtures/visual-critic/candidate.json
```

The recorded offline suite covers hard QR, hard brand, product identity, repairable typography, timeout, low confidence, self-approval and clean pass.

Live provider evaluation is separate and must never be reported PASS merely because credentials are absent.

## 16. Tests

Implemented executable evidence:

- hard QR fail cannot be hidden by aesthetics；
- hard brand font fail；
- product identity hard fail；
- deterministic resolution hard fail；
- typography overflow -> `RESIZE_NODE` repair；
- grader timeout -> review；
- low confidence -> review；
- calibration dataset drift -> review；
- same model/prompt self-approval -> review；
- hard constraint runtime unavailable -> review, never PASS；
- exact Artifact persistence + normalized score；
- cross-project attachment rejection；
- calibration metric recomputation；
- deterministic 2k-node scale harness。

## 17. CI

`.github/workflows/visual-critic.yml` jobs:

```text
critic-contract
critic-quality
critic-integration
critic-calibration
critic-db
critic-benchmark
```

Completion requires every required hosted job to actually execute green.

A GitHub billing/spending-limit zero-step runner failure is an external blocker, not PASS and not an observed code/test failure.

## 18. Acceptance status

- [x] deterministic signals implemented first in runtime path.
- [x] hard gates dominate weighted score.
- [x] critique and repairs are structured DesignOperations.
- [x] grader/model/prompt/calibration versions are recorded.
- [x] timeout/unavailable/low-confidence cannot silently PASS an active profile.
- [x] Artifact/DB persistence contracts implemented.
- [x] NODE-05 offline gate dataset committed.
- [ ] hosted TypeScript/unit/integration/calibration/DB/benchmark jobs execute green.
- [ ] production visual grader has a real human-labeled calibration dataset before production approval use.

## 19. Definition of Done

```text
quality engine implemented                          IMPLEMENTED
calibration contract + offline release gate         IMPLEMENTED
Artifact/DB integration                             IMPLEMENTED
hosted validation executed green                    PENDING
production VLM human calibration                    REQUIRED BEFORE LIVE AUTO-APPROVAL
```

Current node status remains **IMPLEMENTED / VALIDATING / not COMPLETE** until hosted gates actually execute.

下一节点：NODE-51 Auto Repair Loop。

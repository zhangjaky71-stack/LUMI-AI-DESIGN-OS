# NODE-43 — Brand Rules Engine

> Phase: 5 Design Intelligence  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0/P1 CORE QUALITY  
> Depends on: NODE-14, NODE-17, NODE-18, NODE-34, NODE-39, NODE-42  
> Produces: versioned Brand Profile/Tokens/Assets/Rules, pinned BrandContext, deterministic compliance, governed guide extraction, Constraint + Artifact approval integration

---

## 1. Goal

Turn brand knowledge into an executable, versioned system of record. Brand Rules Engine must prevent Agents from treating brand guidance as prompt-only prose while avoiding a second mutation/enforcement engine.

Frozen boundaries:

- NODE-18 owns verified binary assets and font rights metadata.
- NODE-38 owns Design IR and DesignOperation mutation protocol.
- NODE-39 owns server-side hard-constraint enforcement.
- NODE-34 owns context selection/packing; NODE-43 provides a pinned structured BrandContext.
- NODE-42 owns ArtifactVersion and approval lifecycle; NODE-43 supplies exact brand version + compliance gate.

## 2. Runtime model

Implemented contracts live in `packages/brand-rules/src/types.ts`:

```text
BrandProfile
BrandTokenSet
BrandAssetSet
BrandRuleSet
BrandRule
BrandVoice
BrandVisualReferenceSet
BrandContext
BrandDiagnostic
BrandComplianceReport
BrandGuideExtractionProposal
```

Rule severities are `HARD | SOFT | ADVISORY` and preserve NODE-14 semantics.

Rule sources are frozen as:

```text
USER_EXPLICIT
APPROVED_GUIDE_EXTRACTION
MANUAL_ADMIN
INFERRED_PROPOSAL
```

## 3. Versioning

Every published BrandRuleSet points to exact `token_set_version` and `asset_set_version`. Compliance rejects stale/mismatched dependencies instead of silently evaluating a newer token/asset set.

ArtifactVersion and Artifact provenance now carry `brand_rule_set_version`. Historical artifacts are therefore evaluated/explained against the brand version that was active when the candidate was produced.

## 4. Brand tokens and assets

P0 token model supports:

- colors and semantic roles;
- verified font asset ids and fallbacks;
- spacing scale;
- radius token extension point.

P0 asset model supports:

- logo assets;
- font assets;
- positive visual references;
- negative visual references.

Asset bytes, MIME verification, scanning, licensing and signed URLs remain NODE-18 responsibilities.

## 5. Deterministic rule runtime

`packages/brand-rules/src/runtime.ts` evaluates Design IR directly for rules that do not need a model:

```text
ALLOWED_COLOR_TOKENS
FORBIDDEN_COLORS
ALLOWED_FONT_ASSETS
MIN_TEXT_SIZE
REQUIRE_TOKEN_BINDING
ALLOWED_LOGO_ASSETS
LOGO_MIN_SIZE
LOGO_CLEAR_SPACE
LOGO_FORBID_ROTATION
LOGO_FORBID_STRETCH
LOGO_FORBID_RECOLOR
ALLOWED_ASSETS
SPACING_SCALE
VOICE_FORBIDDEN_TERMS
```

The runtime also checks verified asset ids and font-rights availability when supplied by NODE-18 adapters.

Deterministic evaluation is stable: rule order is priority-descending then rule id; nodes are id-sorted.

## 6. Auto-fix boundary

Brand Rules Engine never mutates Design IR directly. Repair suggestions are NODE-38 `DesignOperation[]` using the current document version:

```text
BrandDiagnostic
  -> repair_operations[]
  -> NODE-39 preflight
  -> NODE-38 executor
```

This prevents brand auto-fix from bypassing user locks or other hard constraints.

## 7. Brand Guide / PDF extraction governance

Automated extraction is not an authority boundary.

```text
guide/pdf
→ candidate + confidence + citation
→ INFERRED_PROPOSAL
→ human review
→ APPROVED_GUIDE_EXTRACTION
→ next rule-set draft
→ publish
```

P0 invariants:

- unreviewed candidate requires exact source citation;
- `INFERRED_PROPOSAL` cannot be HARD;
- human reviewer identity is required before approval;
- a reviewer may intentionally promote an approved candidate to HARD;
- a published BrandRuleSet cannot contain unreviewed inferred proposals.

These invariants are repeated in TypeScript, Python and PostgreSQL.

## 8. NODE-39 Constraint integration

`BrandConstraintAdapter` implements the frozen `BrandComplianceValidator` interface for `REQUIRE_BRAND_COMPLIANCE` / `LOCK_BRAND`.

It resolves an exact BrandEvaluationContext, maps diagnostics into NODE-39 `ConstraintViolation`, and returns `VALIDATION_UNAVAILABLE` if the brand repository/evaluator is unavailable. Hard brand validation therefore fails closed rather than becoming PASS because a validator crashed.

## 9. NODE-34 Context integration

`buildBrandContext()` accepts only a PUBLISHED rule set whose token/asset versions match. Output is always `pinned: true` and contains:

- exact BrandRuleSet id/version;
- active hard rules;
- selected color/font/spacing tokens;
- allowed asset ids;
- voice summary;
- visual reference ids.

Approved brand facts therefore survive context compaction and invalidate naturally by version.

## 10. NODE-42 Artifact approval integration

`evaluateBrandApprovalGate()` denies approval when:

```text
brand_rule_set_version missing
OR artifact/report brand version mismatch
OR hard brand violations exist
```

Approved historical artifacts are not overwritten when a newer BrandRuleSet publishes.

## 11. Visual / semantic brand rules

`VISUAL_STYLE_GUIDANCE`, photographic direction and semantic identity remain model-grader plugin territory. They are primarily SOFT/ADVISORY in NODE-43.

NODE-43 does not claim deterministic logo/product identity from an LLM. NODE-44 Identity Engine owns similarity/identity scoring.

## 12. Python parity

`services/brand-rules` provides a dependency-free Python reference runtime with:

- the same source/severity publication invariants;
- deterministic compliance for high-value color/font/logo/binding/asset/voice rules;
- BrandContext generation;
- extraction proposal review;
- version mismatch fail-closed behavior.

The service is intentionally standalone, matching `services/artifact-history`, so NODE-43 does not modify the frozen root uv workspace lock.

## 13. Database

`db/migrations/0002_brand_rules.sql` creates:

```text
brand_profiles
brand_token_sets
brand_asset_sets
brand_rule_sets
brand_rules
brand_guide_extraction_proposals
brand_guide_extraction_candidates
```

It also adds `brand_rule_set_version` to `artifact_versions` and `artifact_provenance`.

Tenant-aware composite references, version uniqueness, inferred-HARD CHECK constraints, extraction citation constraints and publish guards are enforced at the database layer.

## 14. Tests

TypeScript tests cover:

- forbidden brand color;
- font allowlist/rights boundary;
- logo clear-space and rotation;
- DesignOperation auto-fix contract;
- pinned BrandContext;
- inferred HARD rejection;
- extraction citation + human promotion to HARD;
- stale dependency version rejection;
- Artifact approval brand-version mismatch;
- NODE-39 adapter mapping and `VALIDATION_UNAVAILABLE` fail-closed behavior.

Python tests mirror the high-value deterministic/governance cases.

## 15. Benchmark

`scripts/benchmark_brand_rules_engine.py` constructs 2,000 Design IR nodes and 40 active rules, runs deterministic compliance five times and gates on median runtime (`1500 ms` hosted default).

No benchmark number is claimed until hosted CI actually executes.

## 16. CI

`.github/workflows/brand-rules-engine.yml` defines:

1. `brand-contract` — compile, architecture validator, TS typecheck.
2. `brand-quality` — TS/Python tests, Ruff, Pyright.
3. `brand-integration` — Constraint + Brand + Artifact boundary regression.
4. `brand-benchmark` — 2k-node / 40-rule deterministic workload.

## 17. Acceptance evidence

- `packages/brand-rules/src/*`
- `services/brand-rules/src/lumi_brand_rules/*`
- `services/brand-rules/tests/test_brand_rules.py`
- `db/migrations/0002_brand_rules.sql`
- `scripts/validate_brand_rules_engine.py`
- `scripts/benchmark_brand_rules_engine.py`
- `docs/runtime/BRAND-RULES-ENGINE-V1.md`
- `reports/nodes/NODE-43/acceptance.md`
- `.github/workflows/brand-rules-engine.yml`

## 18. Completion rule

NODE-43 remains **IMPLEMENTED / VALIDATING / not COMPLETE** until all dedicated hosted gates actually execute green. Runner/billing failures are external validation blockers and must not be reported as code PASS or code failure.

Next node: **NODE-44 — Identity Engine**.

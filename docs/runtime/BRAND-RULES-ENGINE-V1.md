# Brand Rules Engine Runtime V1

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

NODE-43 turns brand knowledge into versioned, executable design rules without creating a second mutation or enforcement engine.

## Runtime boundary

```text
Brand Profile / verified Assets / approved Guide Extraction
  -> BrandTokenSet + BrandAssetSet + BrandRuleSet(versioned)
  -> BrandContext (pinned for Agent context)
  -> deterministic Brand Compliance
  -> BrandDiagnostic + NODE-38 DesignOperation repair proposals
  -> NODE-39 BrandComplianceValidator adapter
  -> NODE-42 Artifact approval gate + exact brand_rule_set_version
```

Brand Rules never mutates Design IR directly. Repair proposals are NODE-38 `DesignOperation[]` and still pass NODE-39 preflight before execution.

## Versioned objects

- `BrandProfile`: tenant/project-scoped logical brand identity.
- `BrandTokenSet`: versioned color, font and spacing tokens.
- `BrandAssetSet`: versioned logo/font/reference asset ids.
- `BrandRuleSet`: immutable published rule version and its exact token/asset versions.
- `BrandVoice`: structured tone/vocabulary guidance.
- `BrandVisualReferenceSet`: positive/negative visual references and style direction.
- `BrandGuideExtractionProposal`: untrusted model/extraction candidates pending review.

A published rule set cannot contain `INFERRED_PROPOSAL`. An inferred proposal can never be HARD before human approval. Approved extracted rules require source citations.

## Deterministic rules in V1

The runtime evaluates rules from Design IR / verified asset metadata before considering any model-based grader:

- allowed / forbidden color rules;
- allowed font assets and font-rights availability;
- minimum text size;
- token binding;
- allowed brand assets / verified asset requirement;
- allowed logo assets;
- logo minimum size;
- logo rotation / stretch / recolor markers;
- logo clear-space geometry;
- spacing scale;
- forbidden voice terms.

`VISUAL_STYLE_GUIDANCE` and other semantic/photographic similarity rules remain SOFT/ADVISORY inputs for later visual graders. NODE-43 does not pretend that an LLM is a deterministic geometry validator.

## Brand Guide extraction governance

```text
PDF / guide / reference asset
  -> extraction candidate + confidence + exact citation
  -> INFERRED_PROPOSAL (SOFT/ADVISORY only)
  -> reviewer selects candidate and severity
  -> APPROVED_GUIDE_EXTRACTION
  -> next BrandRuleSet draft
  -> publish
```

The database repeats these invariants with CHECK constraints and publish guards.

## NODE-39 integration

`BrandConstraintAdapter` implements the frozen `BrandComplianceValidator` plugin boundary. `REQUIRE_BRAND_COMPLIANCE` and `LOCK_BRAND` resolve an exact `BrandEvaluationContext` and map BrandDiagnostics into NODE-39 violations.

If brand context resolution or evaluation is unavailable, the adapter emits `VALIDATION_UNAVAILABLE`; it never converts validator failure into PASS. A HARD constraint therefore remains fail-closed at approval time.

## NODE-34 integration

`buildBrandContext()` accepts only `PUBLISHED` rule sets with matching token/asset versions. It emits a compact `pinned: true` context containing:

- exact `brand_rule_set_version`;
- active hard rules;
- selected tokens;
- allowed assets;
- voice summary;
- visual reference ids.

This is the structured source of truth for Agent context. Semantic memory must not guess a newer brand value.

## NODE-42 integration

`ArtifactVersion` and artifact provenance now carry `brand_rule_set_version`. Approval uses the exact version attached to the artifact candidate. A newer BrandRuleSet does not retroactively alter historical approval evidence.

`evaluateBrandApprovalGate()` denies approval when:

- no brand rule version is recorded;
- report version and ArtifactVersion differ;
- the compliance report contains a hard violation.

## Storage and tenant boundary

`db/migrations/0002_brand_rules.sql` creates versioned brand tables with `organization_id` composite references. Asset ids remain references to NODE-18; binary storage and font/license verification are not duplicated in NODE-43.

## Performance

The deterministic benchmark evaluates a default workload of 2,000 Design IR nodes against 40 active rules for five runs and gates on median runtime. Model-based visual graders are deliberately excluded from this benchmark because they have a separate latency/error budget.

## Non-goals

- no second Design IR mutation engine;
- no direct Canvas/Pixi state mutation;
- no duplicate asset storage;
- no silent extraction-to-HARD promotion;
- no model-based logo identity claim (NODE-44 owns identity similarity);
- no retroactive rewrite of historical ArtifactVersion brand versions.

## Acceptance evidence

See `reports/nodes/NODE-43/acceptance.md` and `.github/workflows/brand-rules-engine.yml`. Hosted gates must actually execute green before NODE-43 may be marked COMPLETE.

# Brand Kit UI Runtime V1

> NODE-58 runtime contract  
> Product surface: `/app/brands`  
> Canonical engine: `@lumi/brand-rules` (NODE-43)  
> Binary lifecycle: Asset Storage (NODE-18)

## 1. Ownership

Brand Kit UI does **not** own a parallel brand model. Product state is a projection/editor over canonical domain objects:

```text
BrandProfile
BrandTokenSet
BrandAssetSet
BrandRuleSet
BrandGuideExtractionProposal
BrandComplianceReport
```

The browser may hold an unsaved edit buffer, but canonical truth remains server-side and versioned.

## 2. Draft contract

Brand edits use an optimistic `draft_revision`.

```text
GET Brand Kit snapshot
→ edit local draft buffer
→ PATCH draft with expected_draft_revision
→ canonical snapshot with revision+1
```

A stale draft revision must fail with conflict semantics. The UI does not silently merge two concurrent brand edits.

## 3. Asset contract

Logo, font, reference and Brand Guide files reuse the NODE-18 upload lifecycle:

```text
POST /assets/uploads
→ presigned PUT
→ complete upload
→ verify / scan / metadata / rights
→ READY | REJECTED
```

Brand Kit never treats a local file selection as a usable asset. Font and logo publication is gated by scan state; active fonts with `UNKNOWN` rights block publishing.

## 4. Logo rules

Product metadata exposed by NODE-58:

```text
variant: PRIMARY | SECONDARY | MONOCHROME | ICON
preferred_background: LIGHT | DARK | ANY
minimum_size_px
safe_zone_ratio
```

These are UI-editable product settings that ultimately feed canonical logo-related Brand Rules.

## 5. Color tokens

Palette state uses `BrandColorToken` and keeps stable token IDs. NODE-58 adds editor guardrails:

- valid HEX normalization;
- duplicate-value warning;
- token roles;
- foreground/background contrast preview.

The UI does not infer a compliance PASS from contrast alone; Brand Rules Engine remains authoritative.

## 6. Typography and rights

Font assets have a separate binary identity (`asset_id`) and token identity. Supported roles are Heading, Body and CJK fallback. Upload metadata includes a rights assertion:

```text
USER_OWNED
LICENSED
UNKNOWN
```

`UNKNOWN` is not converted to commercial-use permission by upload success.

## 7. Brand Guide extraction

Guide import is intentionally multi-stage:

```text
verified PDF Asset
→ BrandGuideExtractionProposal
→ candidate rules + confidence + exact citations
→ human decision for every candidate
→ APPROVED_GUIDE_EXTRACTION rules
→ draft
→ publish
```

Unreviewed extraction candidates cannot be promoted to `HARD`. Human review may promote an approved cited candidate to `HARD`.

## 8. Publishing

Publishing creates an immutable new `BrandRuleSet` version. Draft state then advances to a new draft version.

Example:

```text
Published v1.0.0
Draft 2.0.0-draft
Publish
→ Published v2.0.0
→ Draft 3.0.0-draft
```

Historical published versions remain addressable for old Projects, Runs and Artifacts.

## 9. Project binding

NODE-58 exposes two policies:

### CURRENT_PUBLISHED

At **new Agent Run creation**, resolve the currently published BrandRuleSet and persist that exact version into the Run. A later Brand Kit publish must not hot-change an active Run.

### PINNED

The project references one exact historical BrandRuleSet version. A nonexistent/stale version fails closed.

## 10. Agent Run freeze

Workspace snapshot adds project `brand_binding`, and Agent Run snapshot exposes `brand_rule_set_version`.

```text
Project Brand binding
→ resolve exact BrandRuleSet version
→ create Agent Run
→ AgentRun.brand_rule_set_version = resolved version
→ SSE / pause / resume / retry preserve it
```

The Workspace displays `Brand vX · frozen` when the Run has the canonical pinned value.

## 11. Compliance contract

A Brand check is always scoped to:

```text
artifact_version_id
brand_rule_set_version
```

The UI renders the canonical `BrandComplianceReport`: decision, score, severity counts and diagnostics. It never silently substitutes the latest BrandRuleSet when a requested historical version is missing.

## 12. Canvas diagnostic deep link

Diagnostics with `node_id` link to:

```text
/app/projects/{projectId}/workspace
  ?focusNode={nodeId}
  &brandRuleVersion={exactVersion}
```

When Canvas editor state becomes ready, Workspace validates the node exists, selects it through `CanvasEditorApi`, fits selection, and preserves the compliance BrandRuleSet version as review context.

## 13. Deterministic mode

Only when all of the following are true:

```text
NODE_ENV != production
LUMI_BRAND_KIT_E2E=1
```

NODE-58 uses an in-browser deterministic adapter. It exercises upload states, guide proposals, rights gating, version publishing, current/pinned binding, compliance and stale-version failures without pretending those fixtures are production dependencies.

## 14. Production boundaries

The HTTP Brand Kit gateway defines the frontend integration boundary. It does not claim the production backend endpoints are already deployed. Production readiness requires:

- persistent BrandProfile/TokenSet/AssetSet/RuleSet APIs;
- NODE-18 upload/scanner/rights services;
- guide extraction worker and reviewer identity;
- BrandRuleSet publish transaction;
- project binding persistence;
- Agent Run server-side exact-version resolution;
- artifact compliance execution through NODE-43/NODE-39.

Until those integrations and hosted tests execute green, NODE-58 remains `IMPLEMENTED / VALIDATING / NOT COMPLETE`.

# NODE-58 — Brand Kit Product UI

> Phase: 7 Frontend Product  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0/P1 LOVART-PARITY  
> Depends on: NODE-43 Brand Rules Engine, NODE-18 Asset Storage, NODE-39 Hard Constraint Enforcement, NODE-54 AI Workspace, NODE-57 Agent Timeline  
> Produces: governed Brand Kit editor, Guide review, version publish, Project binding, Agent Run pinning, compliance-to-Canvas workflow

---

## 1. Product goal

NODE-58 turns `/app/brands` from a placeholder into a product-level Brand Kit workspace for non-technical users.

A Brand Kit is **not** a collection of reference images or a prompt fragment. It is a human-manageable frontend over machine-executable canonical domain objects:

```text
BrandProfile
├─ BrandTokenSet
├─ BrandAssetSet
├─ BrandRuleSet
├─ BrandGuideExtractionProposal
└─ BrandComplianceReport
```

Canonical semantics come from NODE-43. Binary identity, scanning and rights come from NODE-18.

---

## 2. Architecture rule

NODE-58 must not create a second brand-rules model.

```text
Brand Kit UI
    ↓ local unsaved edit buffer only
BrandKitGateway
    ↓ versioned API boundary
NODE-43 canonical Brand domain
    ↓
Agent / Prompt Compiler / Generation / QA / Export
```

Browser storage is not canonical truth. `localStorage`, `sessionStorage` and IndexedDB are not used for Brand Kit persistence.

---

## 3. Product surface

Route: `/app/brands`.

Main sections:

1. Overview
2. Assets & Type
3. Voice & Rules
4. Brand Guide
5. Projects & Compliance

Header exposes active brand, Published version, Draft revision/version, dirty/saved state, Save Draft and Publish BrandRuleSet.

---

## 4. Draft revision safety

Every draft mutation is based on `expected_draft_revision`:

```text
read r3
edit
PATCH expected r3
→ canonical r4
```

A stale writer receives `DRAFT_REVISION_CONFLICT`; the UI does not silently overwrite concurrent brand edits.

---

## 5. Palette editor

Uses canonical `BrandColorToken` stable IDs. Implemented guardrails:

- token name;
- HEX value;
- roles;
- `#RGB` → `#RRGGBB` normalization;
- invalid HEX detection;
- duplicate color-value warning;
- white/ink contrast preview.

Contrast preview is advisory UI information and does not replace NODE-43/NODE-39 compliance decisions.

---

## 6. Logo system

Logo assets retain immutable Asset IDs with editable product metadata:

```text
variant: PRIMARY | SECONDARY | MONOCHROME | ICON
preferred_background: LIGHT | DARK | ANY
minimum_size_px
safe_zone_ratio
```

Raster/SVG uploads use the governed Asset layer; SVG sanitization remains NODE-18 responsibility.

---

## 7. Typography and licensing

Supported roles:

```text
HEADING
BODY
CJK_FALLBACK
```

The UI displays filename, family, scan state, rights assertion, license note and assigned role, plus multilingual preview.

Rights values:

```text
USER_OWNED
LICENSED
UNKNOWN
```

If a font is active in `BrandTokenSet.fonts` and rights are `UNKNOWN`, Publish is blocked.

---

## 8. Governed asset upload

NODE-58 reuses NODE-18 rather than creating Brand-specific storage:

```text
POST /assets/uploads
→ presigned PUT
→ POST /assets/uploads/{uploadId}/complete
→ READY | REJECTED
```

Upload metadata includes `brand_profile_id`, purpose, media metadata and rights assertion. A local file is never treated as usable merely because a file picker accepted it.

---

## 9. Visual references

Visual references distinguish intent:

```text
polarity: APPROVED | NEGATIVE
role: PRODUCT | PHOTOGRAPHY | ILLUSTRATION | LAYOUT
```

Approved and negative Asset IDs feed canonical Brand visual-reference/asset fields.

---

## 10. Voice system

The editor manages canonical voice fields:

- tone attributes;
- preferred vocabulary;
- forbidden words/claims;
- Do examples;
- Don’t examples;
- preserved locale overrides.

Forbidden terms are executable through rules such as `VOICE_FORBIDDEN_TERMS` rather than being decorative labels.

---

## 11. Executable Brand rules

Rules expose type, category, severity, source, stable rule ID and active state.

Severity:

```text
HARD
SOFT
ADVISORY
```

Source provenance:

```text
USER_EXPLICIT
APPROVED_GUIDE_EXTRACTION
MANUAL_ADMIN
INFERRED_PROPOSAL
```

An unreviewed `INFERRED_PROPOSAL` is never treated as a production Hard Rule.

---

## 12. Brand Guide PDF workflow

Guide import is review-gated:

```text
PDF Asset
→ NODE-18 verification / scanning
→ extraction proposal
→ candidate rule + confidence + exact source citation
→ user decision for every candidate
→ optional severity adjustment
→ APPROVED_GUIDE_EXTRACTION rules
→ save draft
→ Publish
```

Canonical NODE-43 helpers are reused in deterministic validation:

- `createExtractionProposal()`
- `approveExtractionProposal()`
- `rejectExtractionProposal()`

Invariants:

- every candidate requires citation;
- unreviewed candidate cannot be HARD;
- incomplete review fails;
- human-approved cited candidate may be promoted to HARD;
- rejected candidates never enter the executable draft rule set.

---

## 13. Publishing and immutable history

Example lifecycle:

```text
Published v1.0.0
Draft 2.0.0-draft
Publish
→ Published v2.0.0
→ next Draft 3.0.0-draft
```

Publishing preserves historical versions. Existing Artifacts and pinned Projects can continue to reference older versions.

Publish preflight blocks invalid or duplicate palette values, non-READY logos, non-READY active fonts, active fonts with UNKNOWN rights, active unreviewed inferred rules and inferred HARD rules.

---

## 14. Project Brand binding

### CURRENT_PUBLISHED

The Project means “use current published Brand Kit for the next Run.” At Run creation, the exact version is resolved and written into the Run snapshot.

### PINNED

The Project references one exact published version. Nonexistent versions fail closed with stale-version semantics.

Publishing v2 changes a CURRENT Project’s next resolved version while a PINNED v1 Project remains on v1.

---

## 15. Agent Run version freeze

NODE-58 extends AI Workspace contracts with:

```text
AIWorkspaceSnapshot.brand_binding
AgentRunSnapshot.brand_rule_set_version
```

Run creation passes/resolves the exact Project Brand version and deterministic runtime stores it:

```text
Project resolved Brand v1
→ Start Run
→ AgentRun.brand_rule_set_version = 1.0.0
→ pause/resume/SSE/retry preserve v1
```

Workspace displays `Brand v1.0.0 · next Run` before creation and `Brand v1.0.0 · frozen` after the Run owns the exact version. A later Brand publish does not hot-mutate an active Run.

Production authority remains server-side: the backend must validate the Project binding and persist the resolved version rather than trusting a client-supplied version blindly.

---

## 16. Brand Compliance preview

Brand check requires two exact identities:

```text
artifact_version_id
brand_rule_set_version
```

The UI renders canonical `BrandComplianceReport` fields:

- `PASS / PASS_WITH_WARNINGS / FAIL`;
- score;
- hard/soft/advisory counts;
- rule ID;
- category/severity;
- reason code;
- expected vs actual;
- Canvas node ID when available.

An unavailable historical version fails with `BRAND_RULE_VERSION_STALE`; the UI must not silently substitute latest.

---

## 17. Compliance → Canvas handoff

Diagnostics with a node create a deep link:

```text
/app/projects/{projectId}/workspace
?focusNode={nodeId}
&brandRuleVersion={exactVersion}
```

AI Workspace waits for `CanvasEditorState`, validates the node exists, then uses the existing `CanvasEditorApi` selection/fit commands. There is no parallel Canvas selection state. The exact historical Brand version remains visible as review context.

---

## 18. Deterministic E2E boundary

Enabled only when:

```text
NODE_ENV != production
LUMI_BRAND_KIT_E2E=1
```

Seed includes LUMI Coffee, Published v1.0.0, Draft 2.0.0-draft, palette, logos, licensed Latin/CJK fonts, approved/negative references, CURRENT/PINNED projects and an exact ArtifactVersion compliance fixture.

The deterministic adapter covers governed upload transitions, rejection fixtures, unknown font rights, Guide proposals/review, version publish, binding resolution, exact compliance and stale-version failure. No deterministic fixture is enabled in the production build.

---

## 19. Test matrix

### Unit

- HEX normalization and contrast;
- duplicate tokens;
- unknown active font rights publish block;
- Guide proposal citation and human review;
- approved candidate promotion to HARD;
- immutable publish/version advance;
- CURRENT advances / PINNED stays;
- stale compliance version;
- Agent Run Brand version freeze.

### Browser

- palette edit/save;
- Logo upload;
- font UNKNOWN rights guard;
- Brand Guide import/review;
- publish v2;
- current/pinned resolution;
- compliance score/diagnostics;
- stale rule version;
- compliance deep-link → exact Canvas node;
- Agent Run `Brand vX · frozen`;
- mobile Brand Kit.

NODE-54/55/56/57 remain browser regression dependencies because NODE-58 extends Workspace and Canvas navigation.

---

## 20. Hosted validation

Dedicated workflow:

```text
brand-kit-contract
brand-kit-quality
brand-kit-build
brand-kit-browser-e2e
```

Pinned toolchain: Ubuntu 24.04, Node 24, pnpm 11.4.0, Python 3.12.

Hosted red/yellow status is not interpreted as code failure unless a runner actually executes steps. A billing/spending-limit failure before runner remains a platform blocker.

---

## 21. Production integration boundaries

NODE-58 frontend is implemented, but full production completion still requires real services for:

- Brand Profile/Token/Asset/Rule persistence;
- scanner and rights metadata;
- Guide extraction worker;
- reviewer identity/audit trail;
- atomic BrandRuleSet publish;
- project binding storage;
- server-side authoritative Run Brand version resolution;
- compliance execution against real Design IR / ArtifactVersion;
- production authorization and observability.

Deterministic E2E does not masquerade as those production integrations.

---

## 22. Acceptance checklist

- [x] `/app/brands` is a real product UI.
- [x] Logo/colors/fonts/voice/references/rules are editable.
- [x] Brand files use the governed Asset upload boundary.
- [x] font rights are visible and can block Publish.
- [x] Guide proposals retain exact citations.
- [x] complete human review is required.
- [x] approved Guide rules preserve source provenance.
- [x] BrandRuleSet Publish creates a new version in deterministic runtime.
- [x] CURRENT/PINNED project behavior is represented.
- [x] Agent Run exposes frozen BrandRuleSet version.
- [x] Compliance is scoped to exact ArtifactVersion + BrandRuleSet version.
- [x] stale Brand version fails closed.
- [x] diagnostic can deep-link to Canvas node.
- [x] deterministic unit/browser/static gates are staged.
- [ ] hosted pinned gates have executed green.
- [ ] production Brand APIs and workers are connected.

---

## 23. Definition of Done

```text
brand kit UX E2E green
+ version/publish tests green
+ guide-extraction review flow green
+ Agent Run version freeze green
+ compliance-to-Canvas green
+ hosted pinned gates green
+ production Brand services integrated
```

Until the final hosted/production conditions are true, status remains **IMPLEMENTED / VALIDATING / NOT COMPLETE**.

下一节点：**NODE-59 — Versions UI**。

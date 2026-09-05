# NODE-58 Acceptance Evidence

> Node: Brand Kit Product UI  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Base: `node-57-agent-timeline-release` @ `98d897c443d1d6c6a3ba88d40d209b52d9707357`

## Implemented product surface

- `/app/brands` replaced the placeholder with a real Brand Kit workspace.
- Overview with Brand Profile, Published version, Draft revision and product metrics.
- Palette editor with stable token IDs, HEX normalization, role editing, duplicate warnings and contrast preview.
- Logo system with primary/secondary/monochrome/icon variants, preferred background, min size and safe zone.
- Font upload/roles with multilingual preview, scan state, rights assertion and license notes.
- Approved and Negative visual references with semantic roles.
- Voice editor for tone, vocabulary, forbidden claims and Do/Don't examples.
- Executable BrandRuleSet list with severity/source/active state.
- Brand Guide PDF import with cited extraction proposals and complete human review requirement.
- Draft → immutable Publish version flow.
- Project binding policies: CURRENT_PUBLISHED and PINNED.
- Exact ArtifactVersion × BrandRuleSet compliance preview.
- Diagnostic deep-link to the exact Canvas node.
- Workspace shows Project Brand binding and frozen Agent Run BrandRuleSet version.

## Canonical architecture truth

NODE-58 consumes NODE-43 canonical domain types from `@lumi/brand-rules`:

```text
BrandProfile
BrandTokenSet
BrandAssetSet
BrandRuleSet
BrandGuideExtractionProposal
BrandComplianceReport
```

It does not create a browser brand-rules database or a second semantic rule engine.

## Asset lifecycle truth

Production adapter uses the existing governed flow:

```text
POST /assets/uploads
→ presigned PUT
→ complete
→ scan / metadata / rights
→ READY | REJECTED
```

Logo/font/reference/guide uploads preserve Asset IDs and rights assertions. A local `File` is never treated as canonical usable media merely because it was selected.

## Brand Guide safety truth

Deterministic implementation reuses NODE-43:

```text
createExtractionProposal()
approveExtractionProposal()
rejectExtractionProposal()
```

Validated invariants staged in tests:

- every extracted candidate has a source citation;
- unreviewed extraction is never HARD;
- every candidate requires an explicit human decision;
- only approved candidates enter executable draft rules;
- approved cited candidates may be human-promoted to HARD;
- source becomes `APPROVED_GUIDE_EXTRACTION`.

## Version truth

Seed starts at:

```text
Published BrandRuleSet v1.0.0
Draft 2.0.0-draft
```

Publish produces:

```text
Published v1.0.0 preserved
Published v2.0.0 appended
Draft advances to 3.0.0-draft
```

CURRENT projects resolve v2 for the next Run; PINNED v1 projects remain v1.

## Agent Run freeze truth

AI Workspace contracts now include:

```text
AIWorkspaceSnapshot.brand_binding
AgentRunSnapshot.brand_rule_set_version
```

Run creation stores the resolved version and subsequent run transitions/SSE preserve it. Workspace distinguishes:

```text
Brand v1.0.0 · next Run
Brand v1.0.0 · frozen
```

The UI does not claim an active Run hot-updates after Brand publish. Production remains responsible for authoritatively resolving and validating the Project Brand version at Run creation.

## Compliance truth

Compliance request requires exact:

```text
artifact_version_id
brand_rule_set_version
```

The deterministic report includes a HARD forbidden-color diagnostic on `node-offer` and a SOFT voice diagnostic on `node-headline`. Canonical decisions are `PASS / PASS_WITH_WARNINGS / FAIL`. Unknown historical rule versions fail with `BRAND_RULE_VERSION_STALE` instead of falling back to latest.

Compliance links preserve exact rule version and node:

```text
/workspace?focusNode=node-offer&brandRuleVersion=1.0.0
```

Workspace waits for `CanvasEditorState`, validates the node, selects through existing `CanvasEditorApi`, fits selection, and shows the historical compliance version as context.

## Unit coverage staged

- HEX normalization;
- contrast ratio;
- duplicate palette values;
- active font UNKNOWN rights publish block;
- immutable publish/version advance;
- CURRENT vs PINNED binding behavior;
- cited Guide extraction;
- complete human review;
- approved Guide rule promotion/provenance;
- stale compliance version;
- Agent Run Brand version freeze.

## Browser coverage staged

- palette edit/save;
- governed Logo upload;
- unknown font rights UI + publish guard;
- PDF Guide proposal + incomplete-review guard + approved rule;
- Publish v2;
- CURRENT advances while PINNED stays;
- compliance score and diagnostics;
- stale BrandRuleSet failure;
- diagnostic → exact Canvas node deep link;
- Run exact BrandRuleSet freeze;
- focused mobile surface.

NODE-57 Timeline, NODE-56 Layers/Inspector, NODE-55 Infinite Canvas and NODE-54 AI Workspace remain browser regression dependencies.

## Static gate

```text
python scripts/validate_brand_kit_ui.py
```

The validator checks canonical NODE-43 ownership, NODE-18 upload reuse, rights metadata, guide citation/review safeguards, version publish semantics, current/pinned binding, exact compliance identities, stale-version fail-closed behavior, Canvas deep-link ownership, Agent Run version freeze, browser coverage markers and absence of durable browser canonical storage.

## Hosted workflow

`.github/workflows/brand-kit-ui.yml` defines:

```text
brand-kit-contract
brand-kit-quality
brand-kit-build
brand-kit-browser-e2e
```

Pinned stack:

```text
Ubuntu 24.04
Node 24
pnpm 11.4.0
Python 3.12
```

The contract job runs the entire frontend architecture validator chain and typechecks Brand Rules, Design IR, Canvas SDK and Web. Quality runs canonical Brand Rules tests, Brand Kit tests, AI Workspace regressions, Canvas SDK regressions, lint and formatting. Browser E2E re-runs NODE-58 plus NODE-57 through NODE-54.

## Hosted evidence

Implementation SHA:

```text
c6ffd62d09a64a4cf839f6971895a65e8602060d
```

Brand Kit UI workflow:

```text
run id: 31864299478
run number: 1
```

Jobs observed:

```text
brand-kit-contract       94962777284  failure  steps=null
brand-kit-quality                     skipped  steps=null
brand-kit-build                       skipped  steps=null
brand-kit-browser-e2e                 skipped  steps=null
```

GitHub check annotation for `brand-kit-contract` states:

```text
The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings
```

Therefore the runner did **not** start and none of NODE-58's static/typecheck/unit/lint/build/browser gates executed on GitHub-hosted infrastructure. This is an account billing/spending-limit platform blocker. It is **not** a code/test failure and it is **not** a PASS.

## Production dependency truth

NODE-58 does not claim these production integrations are already complete:

- persistent Brand Profile/Token/Asset/Rule APIs;
- real NODE-18 scanner/rights/font metadata services;
- production Guide extraction worker;
- production reviewer identity/audit trail;
- atomic BrandRuleSet publish transaction;
- production project binding persistence;
- server-side authoritative Run Brand version resolution;
- real ArtifactVersion compliance execution through NODE-43/NODE-39;
- authorization/tenant policy and observability for the above.

The HTTP gateway is an explicit typed integration boundary; deterministic mode is non-production only.

## Current verdict

```text
Brand Kit product route               IMPLEMENTED
canonical NODE-43 model reuse         IMPLEMENTED
palette editor                        IMPLEMENTED
logo system                           IMPLEMENTED
font rights + roles                   IMPLEMENTED
visual references                     IMPLEMENTED
voice + executable rules              IMPLEMENTED
Guide extraction review UX            IMPLEMENTED
versioned publish model               IMPLEMENTED
CURRENT/PINNED binding                IMPLEMENTED
Agent Run Brand version freeze        IMPLEMENTED
compliance preview                    IMPLEMENTED
compliance → Canvas node              IMPLEMENTED
unit/browser coverage                 STAGED
static architecture gate              STAGED
hosted pinned gates                   BLOCKED BEFORE RUNNER
production Brand APIs/workers         INTEGRATION DEPENDENCY
```

NODE-58 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.

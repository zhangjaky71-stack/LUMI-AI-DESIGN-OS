# NODE-56 Acceptance Evidence

> Node: Layers / Inspector UI  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Base: `node-55-infinite-canvas-release` @ `20f9927ac6bf3867b0c4e724fe03627a0b32afdf`

## Implemented product surface

- Right workspace panel replaced with a real `Layers / Inspector` product surface.
- Tabs: Layers / Design / Context.
- Recursive DesignDocument hierarchy with top-most sibling first.
- Search, expand/collapse and inline rename.
- Layers ↔ CanvasSelectionModel bidirectional selection sync.
- Local vs effective visibility and lock state.
- Visibility / lock DesignOperation edits.
- Transform Inspector: X / Y / W / H / rotation.
- Appearance Inspector: opacity / blend / fill.
- Typography Inspector: content / font size / line height / letter spacing / alignment / fill.
- REORDER_NODE z-order actions.
- Real GROUP creation + child MOVE/REPARENT operations.
- Safe zero-rotation Ungroup with child coordinate restoration.
- Duplicate / Delete / Fit selection / AI Edit actions.
- Existing Brand / project reference context preserved.
- Mobile top-level third tab renamed to Inspector.

## Runtime integration truth

The Inspector does not mutate DesignDocument independently and does not call the Canvas save gateway.

It uses:

```text
CanvasEditorApi
→ InfiniteCanvasProduct
→ semantic DesignOperation builders
→ applyLocalOperations()
→ NODE-55 autosave/history/conflict path
```

`CanvasEditorState` is a read projection of the current Canvas runtime snapshot and is never persisted separately.

## Group / Ungroup safety

Group V1 requires unlocked siblings under one direct parent and emits:

```text
CREATE_NODE GROUP
MOVE_NODE into group-local coordinates
REPARENT_NODE into GROUP
```

Ungroup V1 supports one unlocked GROUP with zero rotation and emits:

```text
MOVE_NODE back to parent-local coordinates
REPARENT_NODE to former parent
DELETE_NODE group
```

The zero-rotation boundary prevents incorrect flattening of arbitrary transformed groups.

The existing Canvas SDK semantic history path supports inversion of `CREATE_NODE`, `DELETE_NODE`, `REORDER_NODE` and `REPARENT_NODE`, so NODE-56 hierarchy edits remain compatible with semantic undo/redo rather than bypassing history.

## Unit coverage staged

- layer hierarchy ordering;
- local/effective visibility and lock inheritance;
- group / ungroup eligibility;
- sibling grouping coordinate preservation;
- ungroup coordinate restoration;
- transform semantic operations;
- typography semantic operations.

## Browser coverage staged

- Layers selection equals Canvas + Agent selection;
- visibility/lock autosave;
- Transform and Typography edits;
- actual Group/Ungroup hierarchy;
- inline rename;
- z-order operation;
- Brand/reference Context regression;
- focused mobile Inspector.

NODE-55 Infinite Canvas and NODE-54 AI Workspace browser suites remain regression dependencies. Their selectors were tightened where NODE-56 introduces duplicate visible layer labels/counts so the regressions continue to assert the intended Canvas or Agent surface rather than relying on ambiguous global text matches.

## Static validation definition

```text
python scripts/validate_layers_inspector.py
```

The gate checks one selection truth source, Editor API ownership, DesignOperation mutation paths, Group/Ungroup semantics, effective visibility/lock, saved-state AI gate, mobile coverage and absence of durable browser truth.

## Hosted gate definition

`.github/workflows/layers-inspector.yml` defines:

```text
layers-inspector-contract
layers-inspector-quality
layers-inspector-build
layers-inspector-browser-e2e
```

The workflow uses the repository-pinned Node 24 / pnpm 11.4.0 / TypeScript 6.0.3 toolchain and reruns the upstream Canvas/AI Workspace regression chain.

## Hosted run evidence — 2026-08-15

Draft PR #56 triggered Layers Inspector workflow run `31861676871` against implementation SHA `6221ee204633b289a5a1d9b1f610c1e658c738d1`.

Observed result:

```text
layers-inspector-contract     failure before runner start
steps                         []
runner_id                     0
layers-inspector-quality      skipped
layers-inspector-build        skipped
layers-inspector-browser-e2e  skipped
```

GitHub check-run `94956064484` attached an annotation stating that the job was not started because recent account payments failed or the account spending limit must be increased.

Therefore this run provides **no execution evidence** for the staged static validator, TypeScript, lint, unit tests, Canvas SDK regressions, production build or Playwright. It must not be classified as either a code/test failure or a PASS.

Other workflows attached to the same commit also showed the same repository/account-level Actions condition or remained queued behind it. NODE-56 acceptance remains blocked on actual hosted runner execution.

## Production dependency truth

NODE-56 builds on NODE-55's typed Canvas save adapter. It does not convert that adapter into a claimed production backend.

Remaining production dependencies include:

- canonical Canvas persistence endpoint or formal supersession;
- production renderer parity/performance validation;
- authoritative font inventory/style/rights model for advanced typography.

## Current verdict

```text
Layers tree                     IMPLEMENTED
Canvas selection sync           IMPLEMENTED
Transform Inspector             IMPLEMENTED
Appearance Inspector            IMPLEMENTED
Typography Inspector            IMPLEMENTED
Group / Ungroup                 IMPLEMENTED (safe V1)
NODE-55 autosave integration    IMPLEMENTED
unit/browser coverage           STAGED / NOT EXECUTED BY HOSTED RUNNER
static architecture gate        STAGED / NOT EXECUTED BY HOSTED RUNNER
pinned hosted gates             BLOCKED BEFORE RUNNER START (billing/spend limit)
canonical Canvas backend        UPSTREAM DEPENDENCY
font/style production model     UPSTREAM DEPENDENCY
```

NODE-56 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.

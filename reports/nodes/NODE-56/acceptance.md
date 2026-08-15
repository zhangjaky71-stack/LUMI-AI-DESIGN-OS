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

NODE-55 Infinite Canvas and NODE-54 AI Workspace browser suites remain regression dependencies.

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

## Known hosted infrastructure blocker

NODE-53, NODE-54 and NODE-55 GitHub Actions were observed failing before a runner started because recent account payments failed or the repository/account spending limit needed to be increased.

NODE-56 must be evaluated the same way: if its first job has no executed steps and receives the same GitHub billing annotation, that is a hosted execution blocker, not a code/test failure or a PASS.

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
unit/browser coverage           STAGED
static architecture gate        STAGED
pinned hosted gates             PENDING EXECUTION
canonical Canvas backend        UPSTREAM DEPENDENCY
font/style production model     UPSTREAM DEPENDENCY
```

NODE-56 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.

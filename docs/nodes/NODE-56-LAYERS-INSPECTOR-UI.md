# NODE-56 — Layers / Inspector UI

> Phase: 7 Frontend Product  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0 / CORE EDITOR UX  
> Depends on: NODE-38, NODE-40, NODE-41, NODE-54, NODE-55  
> Produces: professional Layers tree, selection-synced Inspector, semantic DesignOperation editing

---

## 1. Goal

Turn the NODE-55 Infinite Canvas into a professional editor surface by adding a real Layers tree and property Inspector that operate on the same DesignDocument and CanvasController state as the Canvas.

NODE-56 must not introduce a parallel persistence model.

The governing rule is:

```text
Layers / Inspector UI
→ CanvasEditorApi
→ DesignOperation builders
→ Canvas applyLocalOperations()
→ NODE-55 autosave buffer
→ versioned canonical save
```

Every editable property therefore inherits NODE-55 undo/history, batching, offline state and document-version conflict semantics.

## 2. Product layout

The existing workspace remains:

```text
Agent | Infinite Canvas | Layers / Inspector
```

The right panel has three focused tabs:

```text
Layers
Design
Context
```

Mobile keeps the parent workspace's focused panel model and renames the third top-level tab to `Inspector`.

## 3. Layers tree

Implemented P0 behavior:

- recursive DesignDocument hierarchy;
- frame/group/text/image/shape glyphs;
- top-most visual layer displayed first;
- expand/collapse;
- search by name, id or kind while preserving matching ancestors;
- selection synchronization with CanvasSelectionModel;
- Shift multi-selection;
- inline rename;
- local visibility toggle;
- local lock toggle;
- separate local vs effective visibility/lock state;
- Group / Ungroup actions.

The tree is derived from `DesignDocument.nodes` rather than from DOM children or renderer display objects.

## 4. Local vs effective visibility and lock

Design IR stores local node fields:

```text
visible
locked
```

CanvasCompiler computes effective values through ancestor inheritance.

NODE-56 surfaces both concepts:

- `visible` / `locked`: property directly stored on the node;
- `effective_visible` / `effective_locked`: runtime result after parent inheritance.

A child can therefore be locally visible but effectively hidden because its parent is hidden. Likewise a child can be locally unlocked while effectively locked by an ancestor.

This distinction prevents the Inspector from incorrectly writing child properties merely to compensate for parent state.

## 5. Editor bridge

`InfiniteCanvasProduct` now publishes a derived `CanvasEditorState` containing:

```text
document_id
server_document_version
local_document_version
sync_state
selected_ids
primary_id
layers[]
selected_nodes[]
can_group
can_ungroup
```

It also exposes a narrow `CanvasEditorApi`:

```text
select
renameNode
setVisibility
setLocked
setOpacity
setBlendMode
setFill
setTransform
setText
moveLayer
groupSelection
ungroupSelection
duplicateSelection
deleteSelection
fitSelection
```

The bridge never exposes CanvasController internals directly to the Inspector component.

## 6. Selection truth

Canvas remains the selection owner.

```text
Layer click
→ CanvasEditorApi.select()
→ CanvasSelectionModel
→ Canvas runtime snapshot
→ Agent context + Inspector state
```

Canvas clicks follow the reverse direction through the same state projection.

No separate `selectedLayerIds` persistence exists.

## 7. Design Inspector — Transform

For a single selected node, NODE-56 exposes:

```text
X
Y
W
H
Rotation
Bring forward
Send backward
Fit selection
```

Transform changes are built as semantic operations:

```text
MOVE_NODE
RESIZE_NODE
ROTATE_NODE
REORDER_NODE
```

Width/height are clamped to non-negative values before execution.

Multi-selection intentionally does not fake one shared X/Y/W/H value in V1.

## 8. Design Inspector — Appearance

Implemented:

```text
Visible
Locked
Opacity
Blend mode
Fill
```

Opacity is normalized to `[0, 1]` in Design IR.

Supported initial blend values:

```text
normal
multiply
screen
overlay
darken
lighten
```

Fill is stored in `metadata.fill`, consistent with the existing NODE-55 deterministic Canvas seed and DOM host.

Canvas rendering now also applies node opacity and blend mode from Design IR.

## 9. Design Inspector — Typography

For TEXT nodes:

```text
content
font size
line height
letter spacing
alignment
fill
```

Operations:

```text
SET_TEXT
SET_PROPERTY metadata.font_size
SET_PROPERTY metadata.line_height
SET_PROPERTY metadata.letter_spacing
SET_PROPERTY metadata.text_align
SET_PROPERTY metadata.fill
```

The Canvas product host reflects these values immediately after the DesignDocument transaction succeeds.

Font-family/weight asset resolution remains outside NODE-56 because production font inventory/rights integration requires a dedicated source-of-truth contract.

## 10. Rename and node identity

Layer rename changes only:

```text
name
```

Node ID remains immutable from the product UI. Agent selection and Artifact references continue to use stable node IDs.

## 11. Group

Grouping is a real Design IR hierarchy change.

P0 preconditions:

- at least two selected nodes;
- all selected nodes share the same parent;
- selected nodes are locally unlocked;
- no selected ancestor/descendant overlap.

Transaction:

```text
CREATE_NODE kind=GROUP
MOVE_NODE child coordinates into group-local space
REPARENT_NODE each child under the new group
```

The group bounds are the union of selected sibling transforms.

After commit, selection becomes the new group ID.

## 12. Ungroup

P0 ungroup supports one selected unlocked GROUP with zero group rotation.

Transaction:

```text
MOVE_NODE children back to parent-local coordinates
REPARENT_NODE children to former group parent
DELETE_NODE group
```

Selection becomes the former child IDs.

Rotated groups are deliberately not silently flattened because correct matrix decomposition must preserve transforms; that becomes a later transform/runtime enhancement rather than an unsafe approximation.

## 13. Z-order

Layer order follows the Design IR parent's `children` list.

The Layers tree displays that list in reverse so visually top-most siblings appear first, consistent with professional design tools.

`Bring forward` and `Send backward` emit `REORDER_NODE` operations; they do not directly reorder DOM nodes.

## 14. Autosave and conflicts

Inspector changes do not call the Canvas HTTP gateway directly.

They call `applyLocalOperations()`, therefore they inherit:

- semantic history;
- NODE-55 in-memory autosave batching;
- server-base-version rebasing;
- offline state;
- explicit `DOCUMENT_VERSION_CONFLICT` handling;
- Rebase / Reload recovery.

AI Send remains blocked while Canvas sync state is not `SAVED`.

## 15. Context tab

The old right-panel Project Context functionality is preserved inside the new Inspector:

- Brand Kit label;
- READY reference selection;
- reference role/status;
- safe-context disclosure;
- explicit statement that private chain-of-thought/system prompt are not exposed.

## 16. Rendering integration

The current DOM product host now also projects:

- node opacity;
- blend mode;
- text line height;
- text letter spacing;
- text alignment.

This remains a product integration host on top of the existing Canvas Compiler/SDK architecture. It does not redefine the lower renderer truth model.

## 17. Test matrix

Unit:

- top-most layer ordering;
- local vs effective visibility/lock;
- group eligibility;
- ungroup eligibility;
- sibling grouping preserves coordinates;
- ungroup restores coordinates;
- transform operation generation;
- typography operation generation.

Playwright:

- Layer selection ↔ Canvas ↔ Agent context;
- visibility and lock autosave;
- Transform + Typography editing;
- real Group / Ungroup hierarchy;
- inline rename;
- z-order command;
- Context tab regression;
- mobile Inspector tab.

NODE-55 and NODE-54 browser suites remain regression dependencies.

## 18. CI

Workflow: `.github/workflows/layers-inspector.yml`

Gates:

```text
layers-inspector-contract
layers-inspector-quality
layers-inspector-build
layers-inspector-browser-e2e
```

The workflow also reruns:

- App Shell validator;
- Projects validator;
- AI Workspace validator;
- Infinite Canvas validator;
- Design IR typecheck;
- Canvas SDK typecheck/tests;
- NODE-55 unit/browser regressions;
- NODE-54 browser regressions.

## 19. Acceptance checklist

- [x] Layers tree is derived from DesignDocument hierarchy.
- [x] Layers and Canvas use one selection truth source.
- [x] local/effective visibility and lock are distinguished.
- [x] inline rename preserves stable node ID.
- [x] visibility/lock edits use DesignOperations.
- [x] Transform inspector uses MOVE/RESIZE/ROTATE.
- [x] Appearance inspector covers opacity/blend/fill.
- [x] Typography inspector edits TEXT semantics.
- [x] z-order uses REORDER_NODE.
- [x] Group creates a real GROUP node and reparents children.
- [x] Ungroup reparents children and deletes GROUP.
- [x] Inspector changes use NODE-55 autosave/conflict path.
- [x] Agent Send remains gated on SAVED Canvas state.
- [x] Project Context remains available.
- [x] mobile exposes focused Inspector tab.
- [ ] pinned hosted typecheck/lint/unit/build/Playwright execute green.
- [ ] canonical production Canvas persistence endpoint is connected or formally superseded.
- [ ] full font/style asset model is connected for production typography.

## 20. Definition of Done

Current state:

```text
Layers tree                    IMPLEMENTED
Canvas selection sync          IMPLEMENTED
Transform Inspector            IMPLEMENTED
Appearance Inspector           IMPLEMENTED
Typography Inspector           IMPLEMENTED
Group / Ungroup                IMPLEMENTED (safe V1 boundary)
NODE-55 autosave integration   IMPLEMENTED
hosted frontend gates          PENDING EXECUTION
canonical Canvas backend       UPSTREAM DEPENDENCY
full typography asset model    UPSTREAM DEPENDENCY
```

NODE-56 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until required hosted gates execute green and production dependencies are connected or formally superseded.

Next node: **NODE-57 — Assets / References UI**.

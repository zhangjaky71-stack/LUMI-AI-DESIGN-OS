# Layers / Inspector Runtime V1

> NODE-56 runtime contract  
> Status: implemented frontend editor bridge; hosted validation and production dependencies pending

## 1. Ownership

`DesignDocument` remains the only editable document truth source.

```text
CanvasController owns selection/runtime
Design IR owns document semantics
LayersInspector owns presentation/forms only
NODE-55 owns autosave/version conflict
```

The Inspector never executes Design IR or calls the persistence gateway directly.

## 2. CanvasEditorState

The Canvas projects a safe read model:

```text
document_id
server_document_version
local_document_version
sync_state
selected_ids
primary_id
layers
selected_nodes
can_group
can_ungroup
```

This read model is rebuilt from the current Canvas runtime snapshot. It is not separately persisted.

## 3. CanvasEditorApi

The Canvas exposes a narrow command surface:

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

The API prevents the right panel from acquiring direct mutable access to CanvasController or the gateway.

## 4. Layer projection

Layers are recursively derived from `document.root_id` and `node.children`.

Sibling display order is reversed from Design IR child order so the top-most painted sibling appears first in the Layers panel.

Each row carries:

```text
local visible / locked
effective visible / locked
selected
primary
kind
parent
children
```

Effective values come from the Canvas compiler scene snapshot.

## 5. Selection

Layers never maintain a second canonical selection array.

```text
Layers click -> CanvasEditorApi.select -> CanvasSelectionModel
Canvas click -> CanvasSelectionModel
Canvas snapshot -> CanvasEditorState -> Layers highlighted rows
```

The parent AI Workspace continues to receive the same exact selected node IDs.

## 6. Property mutation

Inspector forms build semantic operations and send them back into Canvas `applyLocalOperations()`.

Examples:

```text
name                 SET_PROPERTY
visible              SET_PROPERTY
locked               SET_PROPERTY
opacity              SET_PROPERTY
blend_mode           SET_PROPERTY
metadata.fill        SET_PROPERTY
x/y                  MOVE_NODE
width/height         RESIZE_NODE
rotation             ROTATE_NODE
text content         SET_TEXT
typography metadata  SET_PROPERTY
z-order              REORDER_NODE
```

Every transaction is re-versioned by the Canvas local operation path before execution.

## 7. Group transaction

Group preconditions:

- two or more nodes;
- same direct parent;
- no locked selected node;
- no ancestor/descendant overlap.

The group is created at the minimum selected sibling index. Its local bounds are the selected union.

Each child is moved into group-local coordinates and then reparented.

All operations share one expected local document version and are applied atomically.

## 8. Ungroup transaction

V1 only flattens one unlocked, zero-rotation GROUP.

Children are translated from group-local to former-parent-local coordinates, reparented, then the empty group is deleted.

The zero-rotation restriction is intentional. Arbitrary rotated/skewed group flattening requires full matrix decomposition and must not be approximated by simple X/Y addition.

## 9. Typography

V1 typography fields are represented using existing Design IR node content plus metadata:

```text
content
metadata.font_size
metadata.line_height
metadata.letter_spacing
metadata.text_align
metadata.fill
```

The product host consumes these values immediately.

Production font-family/weight/style asset resolution is outside this contract until the font inventory/rights model is authoritative.

## 10. Appearance

V1 exposes:

```text
visible
locked
opacity
blend_mode
metadata.fill
```

Opacity is clamped to `[0,1]` before entering Design IR.

The DOM product host applies opacity and blend mode; the Canvas compiler render key already includes them.

## 11. Autosave

The Inspector has no independent save queue.

All accepted Inspector transactions flow into `CanvasAutosaveBuffer`, so they inherit:

```text
debounced batching
server base version rebasing
prefix acknowledgement
OFFLINE state
DOCUMENT_VERSION_CONFLICT
explicit Rebase / Reload
before-unload pending command guard
```

## 12. AI safety boundary

Agent edit context continues to use:

```text
exact CanvasSelectionModel IDs
last saved server document version
```

`DIRTY`, `SAVING`, `OFFLINE` and `CONFLICT` continue to block AI Send.

Inspector local form state never becomes Agent truth.

## 13. Mobile

The parent workspace's third focused mobile tab is `Inspector`.

Inside it, the same Layers / Design / Context tabs are available; NODE-56 does not create a reduced alternate data model for mobile.

## 14. Validation

Static:

```text
python scripts/validate_layers_inspector.py
```

Hosted:

```text
layers-inspector-contract
layers-inspector-quality
layers-inspector-build
layers-inspector-browser-e2e
```

The chain also revalidates NODE-54 and NODE-55.

## 15. Completion boundary

NODE-56 remains `IMPLEMENTED / VALIDATING / NOT COMPLETE` until:

- pinned hosted gates execute green;
- canonical Canvas persistence is production-connected or formally superseded;
- the production typography asset/font model is authoritative for advanced typography controls.

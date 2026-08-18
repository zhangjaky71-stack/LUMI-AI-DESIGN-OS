# Layers / Inspector Runtime Contract V1

Status: NODE-56 core implemented, validating, not complete.

## 1. Truth boundaries

```text
PostgreSQL Python Design IR
        │ canonical immutable versions
        ▼
Canvas Projection V1
        │ browser-only normalization
        ▼
CanvasController.document
        ├─ renderer scene
        ├─ Layers projection
        └─ Inspector projection
```

Layers and Inspector MUST NOT create a second persisted document model. They read the same local `CanvasController.document` used by the Canvas renderer and emit `OperationDescriptor` values through the NODE-55 command/autosave path.

## 2. Selection contract

Canvas and Layers share `CanvasController.selection`.

- Canvas hit-test updates the controller selection and mirrors IDs to React.
- Layer selection calls `selection.set/toggle`, rerenders Canvas, then mirrors IDs to React.
- Inspector receives only those mirrored IDs.
- No selection is stored in localStorage/sessionStorage or persisted into Design IR.
- Agent selection remains a separate exact-version handoff: it is emitted only while autosave state is `saved`, with the server-acknowledged DesignDocument revision.

## 3. Layer tree projection

Layer rows are derived from `DesignDocument.root_id` and ordered `children` arrays.

V1 supports:

- collapse/expand;
- name/role/kind/tag search;
- select and additive select;
- selected-node scroll reveal;
- rename;
- visibility toggle;
- lock/unlock;
- fixed-row virtualization.

The virtualizer uses 30px rows and bounded overscan. A 10k document therefore keeps rendered DOM rows proportional to viewport size rather than document size.

Hierarchy mutation (`REORDER_NODE`, `REPARENT_NODE`, group/ungroup) remains closed until the browser descriptor → Python DesignOperation compiler supports those operations atomically.

## 4. Inspector edit contract

Inspector edits use the same Canvas SDK operation types:

- `MOVE_NODE` for x/y;
- `RESIZE_NODE` for width/height;
- `ROTATE_NODE` for rotation;
- `SET_PROPERTY` for name/visible/locked/opacity;
- `SET_TEXT` for text content.

For multi-select numeric changes, the Inspector creates one descriptor per target and calls `CanvasController.commitBatch()`. The SDK applies the batch locally as one Design IR version transition and emits the descriptor array once to NODE-55 autosave.

## 5. Mixed / locked semantics

Common values are derived from selected nodes; unequal values render `Mixed` rather than inventing a representative value.

If any selected node is locked, property batch editing is blocked. NODE-56 does not silently drop locked targets and edit only the remaining nodes. A user who wants a partial edit must explicitly change the selection.

Unlock itself is allowed because the production Python Design IR runtime permits `SetLockOp` to change lock state.

## 6. Constraints

Inspector state is not a security boundary.

- NODE-39/server validation remains authoritative for persisted operations.
- A persisted `locked=true` node is shown as a HARD lock even if its origin is not projected.
- If source metadata is absent, the UI says `UNRESOLVED`; it never guesses USER/BRAND/PROJECT/SYSTEM.
- Future effective-constraint projection may populate `metadata.constraint_summary` with id/type/severity/source/reason.
- Override actions are not exposed until they can be version-fenced to the exact constraint and DesignDocument version.

## 7. Brand binding

NODE-56 reads projected token references when present in `fill.token_ref`, `stroke.paint.token_ref`, or `metadata.brand_bindings`.

The core Inspector does not expose mutation controls for those bound visual properties. This is intentional: direct style editing must later require an explicit choice to update a token binding target or detach the binding. Silent detach is forbidden.

## 8. Local preview vs canonical server revision

React receives the current local `CanvasController.document` so Layers/Inspector update immediately after a successful local operation. This document may temporarily be ahead of the server while autosave is dirty/saving.

When the save queue drains, the server projection replaces the local controller document. Agent selection is invalidated during dirty/saving/offline/conflict and is restored only after this server acknowledgement.

## 9. Failure semantics

- local Design IR failure: no UI document mutation; show rejection;
- autosave queue full/offline: stop accepting additional edits according to NODE-55 policy;
- HTTP 409: freeze writes and require explicit canonical reload;
- constraint failure on server: entire persisted command batch fails;
- mixed locked selection: disable property batch controls before submission;
- unavailable constraint source: display unresolved, never infer;
- unavailable brand binding mutation contract: keep bound style read-only.

## 10. P0 gaps

See `reports/nodes/NODE-56/gap-ledger.json`. Full NODE-56 completion additionally requires hierarchy reorder/reparent/group/ungroup, TextStyle/font editing, effective constraint-source/override projection, explicit brand update/detach, browser E2E and 10k performance evidence.
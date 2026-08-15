# Infinite Canvas Runtime V1

> NODE-55 runtime contract  
> Status: implemented frontend runtime integration; hosted validation and canonical backend integration pending

## 1. Truth source

The product Canvas is backed by the repository's existing Design IR and Canvas SDK.

```text
DesignDocument = data truth
CanvasController = interaction/runtime controller
CanvasCompiler = scene projection
React = product shell and DOM scene host
```

React state never becomes canonical document storage.

## 2. Runtime bootstrap

Server code selects:

```text
http  -> default / production
e2e   -> non-production only + LUMI_INFINITE_CANVAS_E2E=1
```

E2E mode seeds a real DesignDocument with document version 7 and three frames.

## 3. Product route

```text
/app/projects/{projectId}/workspace
```

NODE-55 replaces only the Canvas center surface. Agent, Artifact, Approval and Context UX from NODE-54 remain part of the same route.

## 4. Canvas SDK usage

The product constructs `CanvasController(document)` and uses it for:

- camera state;
- pan;
- wheel zoom;
- fit-all;
- fit-frame;
- fit-selection;
- selection state;
- transform sessions;
- transform constraint commit;
- scene projection.

The product does not implement a separate scene graph.

## 5. DesignOperation transaction model

All persistent local edits eventually become DesignOperations.

Examples:

```text
CREATE_NODE
DELETE_NODE
SET_PROPERTY
MOVE_NODE
RESIZE_NODE
REORDER_NODE
BATCH
```

The Design IR executor treats a submitted operation array as one transaction. Every operation must target the same `expected_document_version`; a successful transaction advances the document version once.

## 6. Autosave buffer

The in-memory buffer tracks:

```text
base server document version
ordered pending DesignOperations
```

Multiple local transactions can temporarily advance the local document version. Before save, all pending operations are rehydrated to the server base version and sent as one atomic server transaction.

The buffer supports prefix acknowledgement so edits made while a save is in flight are not lost.

## 7. Save adapter

V1 typed adapter:

```text
GET  /projects/{projectId}/canvas-document
POST /canvas/documents/{documentId}/operations:batch
```

Save payload:

```text
project_id
document_id
expected_document_version
operations[]
```

The HTTP path is an adapter boundary until canonical backend API generation/integration is complete. The frontend does not claim this adapter alone constitutes backend completion.

## 8. Conflict handling

On `DOCUMENT_VERSION_CONFLICT`, pending local commands remain in memory and sync state becomes `CONFLICT`.

Two explicit recovery paths exist:

### Rebase local commands

1. fetch canonical document;
2. obtain canonical version;
3. rehydrate pending operations to canonical version;
4. execute them locally as one transaction;
5. if valid, keep the rebased result visible;
6. submit the rebased batch.

### Reload canonical

1. fetch canonical document;
2. discard pending commands;
3. clear local history;
4. replace CanvasController document;
5. return to SAVED.

No silent last-write-wins behavior exists.

## 9. Agent context safety

Canvas sends the parent workspace:

```text
selected_node_ids
document_version
sync_state
```

The document version supplied to Agent commands is the last saved server version, not a speculative local-only version.

AI Send is blocked when Canvas is:

```text
DIRTY
SAVING
OFFLINE
CONFLICT
```

This prevents Agent edits from targeting unsaved geometry.

## 10. Transform interaction

During drag:

- CanvasTransformSession computes preview transforms;
- DOM uses transient visual translation;
- no canonical document mutation occurs per pointermove.

On pointer-up:

- session emits DesignOperations;
- CanvasController commits against constraints;
- accepted operations enter history + autosave;
- rejected operations roll back visual preview.

## 11. Undo / redo

History stores semantic forward and inverse DesignOperations.

`invertOperations(beforeDocument, forwardOps)` creates inverse operations. Undo/redo rehydrates those operations to the current local document version before execution and autosave.

This makes undo/redo persistence-aware.

## 12. Selection / lock

Selection is owned by CanvasSelectionModel.

Locked nodes:

- remain selectable;
- are excluded from transformable IDs;
- cannot be deleted through the product menu;
- can be explicitly unlocked.

Exact selection IDs are forwarded to AI Edit.

## 13. Drag sources

READY Asset:

```text
application/x-lumi-asset
{ asset_id, file_name }
```

Artifact:

```text
application/x-lumi-artifact
{ artifact_version_id, title }
```

Drop creates an IMAGE node near the world point. If the point lies inside a frame, the node is created under that frame. Artifact placement preserves exact version metadata.

System files are not treated as already-uploaded Assets. They require the real Asset lifecycle.

## 14. Camera and rendering

World-to-screen transform uses Canvas SDK camera math.

DOM host transform:

```text
translate(-camera.x * zoom, -camera.y * zoom) scale(zoom)
```

Scene nodes use CanvasCompiler-projected world bounds.

The DOM host is an integration surface, not a replacement for the lower-level renderer/compiler architecture. Production Pixi host parity remains a validation dependency.

## 15. Viewport culling

Only visible, padded viewport nodes plus selected nodes are rendered.

At zoom < 0.18, lower-value text/detail nodes are omitted from the DOM candidate list.

The unit suite projects 2,000 Design IR nodes and asserts visible candidates stay bounded.

## 16. Offline boundary

No canonical Canvas state uses `localStorage`, IndexedDB or sessionStorage.

Pending commands exist only in memory for the active session. Offline state blocks Agent Send and browser unload warns while commands are pending.

This is intentionally narrower than offline-first collaborative editing.

## 17. Mobile

The parent workspace keeps NODE-54's focused mobile tabs. The same InfiniteCanvasProduct is mounted in the Canvas tab with compact toolbars, frame navigation and drag-source access.

## 18. Production guard

E2E mode requires both:

```text
NODE_ENV !== production
LUMI_INFINITE_CANVAS_E2E = 1
```

The production workflow scans `.next/static` for the E2E flag name.

## 19. Validation

Static:

```text
python scripts/validate_infinite_canvas.py
```

Hosted:

```text
infinite-canvas-contract
infinite-canvas-quality
infinite-canvas-build
infinite-canvas-browser-e2e
```

The workflow also typechecks/tests `@lumi/design-ir` and `@lumi/canvas-sdk` and reruns NODE-54 AI Workspace browser regressions.

## 20. Completion boundary

NODE-55 is not COMPLETE until:

- pinned hosted typecheck/lint/unit/build/browser jobs execute green;
- canonical production save API is connected or formally superseded;
- product-route renderer parity/performance is validated in the production runtime.

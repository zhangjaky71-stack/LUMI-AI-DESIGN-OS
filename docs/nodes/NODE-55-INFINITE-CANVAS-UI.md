# NODE-55 — Infinite Canvas UI

> Phase: 7 Frontend Product  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0 / CORE EDITOR UX  
> Depends on: NODE-40, NODE-41, NODE-54  
> Produces: product Infinite Canvas surface backed by CanvasController + Design IR operations

---

## 1. Goal

Replace the NODE-54 CSS preview surface with a real product Canvas that reuses the repository's existing `@lumi/canvas-sdk` and `@lumi/design-ir` runtime instead of creating a second renderer/model.

The user must be able to:

```text
navigate an infinite world
work across multiple frames
select and transform objects
create frame presets
drag READY Assets and exact Artifacts onto Canvas
copy/paste/duplicate/delete/lock/arrange
undo/redo/nudge
see autosave state
resolve document-version conflicts explicitly
send exact saved Canvas selection context into AI Edit
```

## 2. Runtime reuse

NODE-55 imports and instantiates:

```text
CanvasController
CanvasTransformSession
CanvasSelectionModel
DesignDocument
DesignOperation
executeOperations
invertOperations
```

The repository already maps `@lumi/canvas-sdk` to workspace source in `apps/web/tsconfig.json`; NODE-55 adds the matching `@lumi/design-ir` source alias rather than changing package dependencies/lockfiles.

Design IR remains the document truth source. React is the product shell and DOM scene host, not a competing persistence model.

## 3. Product workspace integration

The existing route remains:

```text
/app/projects/{projectId}/workspace
```

NODE-54 Agent + Approval UX stays intact. The center panel now mounts `InfiniteCanvasProduct` and sends back:

```text
selected_node_ids
document_version
sync_state
```

AI Send is disabled unless Canvas state is `SAVED`, preventing an AgentRun from targeting unsaved local geometry.

## 4. Multi-frame canvas

The deterministic product seed starts with:

```text
Square / 1:1
Feed / 4:5
Story / 9:16
```

Frame presets:

```text
1:1   1080 × 1080
4:5   1080 × 1350
9:16  1080 × 1920
16:9  1920 × 1080
A4    2480 × 3508
```

A preset only defines frame dimensions and metadata; it does not prescribe layout content.

## 5. Navigation and selection

Implemented:

- select tool;
- hand tool;
- Space/middle-button pan contract;
- wheel zoom through CanvasController;
- zoom +/-;
- Fit all;
- Fit selection;
- frame navigator / fit-frame;
- multi-selection through Shift;
- exact `CanvasSelectionModel` IDs;
- locked nodes excluded from transforms/deletion;
- low-zoom simplification and viewport culling.

## 6. Transform commit model

Drag interaction follows:

```text
pointer-down
→ CanvasController.beginTransform()
→ visual preview only during pointer move
→ CanvasTransformSession.previewMove()
→ pointer-up
→ CanvasController.commitTransform()
→ accepted DesignOperations enter autosave buffer
```

No persistent document write happens on every pointer move.

Keyboard nudge uses the same transform-session/DesignOperation path.

## 7. Context toolbar and menu

P0 implemented:

- selected node name;
- X / Y / W / H readout;
- Lock / Unlock;
- Bring forward / Send backward;
- AI Edit;
- Copy;
- Paste;
- Duplicate;
- Delete with locked-node protection.

Full typography, crop, mask, group/ungroup and richer inspector properties continue into NODE-56.

## 8. Drag and drop

READY project Assets are draggable with:

```text
application/x-lumi-asset
```

Artifact versions are draggable with:

```text
application/x-lumi-artifact
```

Drop creates a Design IR `IMAGE` node under the frame at the world drop point when possible. Artifact drops preserve exact `artifact_version_id` metadata.

System files are not silently persisted as fake assets. The UI explicitly reports that they must enter the Asset lifecycle before canonical Canvas placement.

## 9. Autosave batching

`CanvasAutosaveBuffer` owns in-memory unsubmitted operations.

Multiple local transactions may advance local DesignDocument versions before a server flush. Before save, operations are rebased to the server base version and submitted as one Design IR transaction:

```text
local v7 → v8 → v9
server v7

save transaction:
expected_document_version = 7
all operations expected_document_version = 7
server executes batch atomically
server result = v8
```

This matches the Design IR executor contract where one successful transaction increments document version exactly once.

If new edits occur during a save, only the acknowledged prefix is removed. Remaining operations are rebased onto the returned canonical document and preserved for the next flush.

## 10. Offline behavior

Canonical Canvas state is never moved into browser durable storage.

When offline:

- local commands may remain in the in-memory buffer;
- sync state becomes `OFFLINE`;
- AI Send is blocked;
- browser unload warns when pending commands exist;
- reconnect schedules autosave.

This deliberately limits offline scope rather than pretending full offline collaborative editing exists.

## 11. Version conflict

The save contract binds:

```text
project_id
document_id
expected_document_version
operations[]
```

A stale save returns `DOCUMENT_VERSION_CONFLICT`.

The UI then exposes two explicit choices:

```text
Rebase local commands
Reload canonical
```

Rebase fetches the latest canonical document, rewrites pending operations to the new base version, validates them locally as one transaction, then resubmits.

Reload discards pending commands and history before replacing the local runtime with canonical state.

There is no silent last-write-wins.

## 12. Undo / redo

NODE-55 uses Design IR `invertOperations` to store semantic history entries.

Undo/redo operations are always rehydrated to the current local document version before execution and are themselves added to autosave, so the persisted document follows the visible history action rather than keeping undo purely cosmetic.

## 13. Viewport performance

The React host renders only scene nodes intersecting a padded world viewport plus selected nodes.

At very low zoom, detail is simplified to high-signal FRAME / IMAGE / SHAPE nodes.

A unit fixture projects 2,000 Design IR nodes and asserts the visible DOM candidate set remains bounded.

The Canvas SDK remains responsible for deeper renderer/compiler/spatial-index performance and Pixi host integration. NODE-55 does not rewrite those subsystems.

## 14. Production adapter boundary

Default mode uses typed HTTP adapter contracts:

```text
GET  /projects/{projectId}/canvas-document
POST /canvas/documents/{documentId}/operations:batch
```

The second endpoint is an integration adapter boundary until the canonical backend API contract is connected or formally supersedes it.

Deterministic E2E mode is available only when:

```text
NODE_ENV !== production
LUMI_INFINITE_CANVAS_E2E = 1
```

The production build gate scans client chunks for the server-only flag.

## 15. Test matrix

Unit:

- autosave multi-local-version rebasing;
- in-flight-prefix acknowledgment;
- nested BATCH version rehydration;
- atomic save increments server version once;
- external edit causes document conflict;
- mixed operation versions rejected;
- 2k-node viewport culling;
- selected offscreen node remains renderable.

Playwright:

- 3 initial frames;
- create frame preset + autosave;
- Canvas selection → AI Edit context;
- READY Asset drag/drop;
- locked-node context menu protection;
- explicit version-conflict Rebase flow;
- mobile focused Canvas.

NODE-54 AI Workspace browser tests are rerun as regressions.

## 16. CI

Workflow: `.github/workflows/infinite-canvas.yml`

Gates:

```text
infinite-canvas-contract
infinite-canvas-quality
infinite-canvas-build
infinite-canvas-browser-e2e
```

It runs:

- App Shell / Projects / AI Workspace / Infinite Canvas static validators;
- Design IR typecheck;
- Canvas SDK typecheck + regression tests;
- Web typecheck/lint;
- Infinite Canvas unit tests;
- production Next build;
- NODE-55 Playwright;
- NODE-54 Playwright regressions.

## 17. Acceptance checklist

- [x] existing CanvasController drives the product surface.
- [x] multiple frames exist in one world.
- [x] pan/zoom/fit-frame/fit-selection controls exist.
- [x] frame presets generate Design IR FRAME nodes.
- [x] exact Canvas selection flows into AI Edit context.
- [x] READY Asset and exact Artifact drag payloads are supported.
- [x] transform commits produce DesignOperations.
- [x] autosave batches multiple local transactions safely.
- [x] offline state is visible and bounded.
- [x] document-version conflicts do not silently overwrite.
- [x] explicit Rebase / Reload exists.
- [x] undo/redo are persisted as DesignOperations.
- [x] locked nodes are protected.
- [x] viewport culling has a 2k-node test.
- [ ] pinned hosted typecheck/lint/unit/build/Playwright gates execute green.
- [ ] canonical production Canvas operations API is connected or formally superseded.
- [ ] production Pixi host/render parity is validated through the product route.

## 18. Definition of Done

Current state:

```text
product Canvas integration       IMPLEMENTED
CanvasController / Design IR     REUSED
multi-frame navigation           IMPLEMENTED
autosave + conflict semantics    IMPLEMENTED
AI selection integration         IMPLEMENTED
hosted frontend gates            PENDING EXECUTION
canonical save backend           UPSTREAM DEPENDENCY
production renderer parity       VALIDATION DEPENDENCY
```

NODE-55 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until pinned hosted gates execute green and production Canvas persistence/render integration is verified.

Next node: **NODE-56 — Layers / Inspector UI**.

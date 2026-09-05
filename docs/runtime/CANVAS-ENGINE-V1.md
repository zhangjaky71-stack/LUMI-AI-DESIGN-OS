# LUMI Canvas Engine Runtime V1

> Node: NODE-40  
> Status: IMPLEMENTED / VALIDATING / not COMPLETE  
> Depends on: NODE-08 Canvas Technology Spike, NODE-38 Design IR Runtime, NODE-39 Constraint Validator

## 1. Runtime boundary

Canvas Engine is an execution/view layer over Design IR. The persisted document is never a Pixi scene graph.

```text
DesignDocument (NODE-38 source of truth)
  -> CanvasSceneSnapshot (derived, disposable)
  -> CanvasSpatialIndex / Selection / Camera
  -> PixiV8RendererAdapter
  -> PixiJS v8 objects / GPU resources
```

Mutation path:

```text
pointer / keyboard / DOM editor
  -> local preview
  -> DesignOperation[]
  -> NODE-39 guardedExecute
  -> accepted DesignDocument or rollback
```

Hard rules therefore cannot be bypassed by drag, paste, undo/redo or text editing.

## 2. Production modules

- `matrix.ts`: affine transform math aligned to Design IR `rotation_deg`.
- `ir-scene.ts`: deterministic IR-to-scene projection and diagnostics.
- `spatial-index.ts`: viewport query and hit testing.
- `selection.ts`: click, multi-select, marquee, select-through and isolation.
- `snapping.ts`: node/frame edge and center candidates plus grid fallback.
- `camera.ts`: infinite pan/zoom, zoom-to-cursor, fit frame/selection/all and DPR helpers.
- `transform-session.ts`: local move/resize/rotate preview and constraint-aware commit.
- `command-bus.ts`: constraint-aware dispatch, undo and redo.
- `renderer.ts`: renderer-neutral adapter and incremental dirty sync.
- `pixi-v8-bindings.ts`: concrete PixiJS v8 structural bridge.
- `resource-manager.ts`: authorized asset resolution, reference counts and GPU disposal.
- `text-edit.ts`: DOM text edit contract, Chinese IME and grapheme handling.
- `clipboard.ts`: Design IR fragments, runtime metadata stripping and cross-project asset policy.
- `keyboard.ts`: P0 editor shortcuts without hijacking text input.
- `controller.ts`: camera/selection/render/commands/constraints orchestration.
- `runtime-benchmark.ts`: 2k/10k synchronous frame-work regression harness.

The original NODE-08 `SpikeSceneStore` remains only as a compatibility/prototype layer. Production NODE-40 state flows from `DesignDocument`.

## 3. Camera and viewport

Camera state is user view state:

```text
camera.x
camera.y
camera.zoom
```

It does not rewrite every DesignNode transform. World-to-screen is:

```text
screen.x = (world.x - camera.x) * zoom
screen.y = (world.y - camera.y) * zoom
```

`CanvasController.renderNow()` applies the camera to the renderer stage and independently queries the spatial index for the current world viewport. Pan/zoom therefore changes both actual Pixi presentation and culling residency.

DPR affects physical renderer resolution only; Design IR geometry remains in logical world pixels.

## 4. Scene projection and error isolation

`projectDesignDocument()` traverses the IR root and produces immutable/disposable scene records with:

- local/world affine matrices;
- local/world bounds;
- paint order;
- visibility/lock state;
- content/asset references;
- deterministic render key.

Malformed inputs produce diagnostics such as:

```text
MISSING_PARENT
MISSING_CHILD
CYCLE
UNSUPPORTED_KIND
```

A malformed or future custom node does not crash the entire projection. Renderer adapters can show a placeholder while the rest of the document remains interactive.

## 5. Selection and hit testing

P0 behavior:

- click topmost node;
- add/toggle multi-select;
- marquee selection;
- cycle/select-through using hit stack offset;
- group/frame/component/instance isolation;
- locked nodes remain selectable but are removed from transform targets;
- `accessibleRows()` exposes an equivalent DOM-friendly Layers representation.

Spatial queries use a uniform world grid rather than scanning the whole document on every pointer event.

## 6. Transform transaction

High-frequency pointer motion stays outside persisted state.

```text
pointerdown
  -> CanvasTransformSession
pointermove
  -> previewMove / previewResize / previewRotate
  -> local candidate only
pointerup
  -> MOVE_NODE / RESIZE_NODE / ROTATE_NODE
  -> guardedExecute
  -> ALLOW: persist candidate
  -> DENY: original document remains authoritative
```

Multi-selection resize converts world target positions through inverse parent matrices so nested nodes retain local transforms.

## 7. Constraint-aware history

Undo/redo is not a snapshot restore. `CanvasCommandBus` builds inverse or replay Design Operations with the current document version and runs them through NODE-39 again.

This matters when constraints changed after the original edit. Example:

```text
move node
-> later user locks current position
-> Undo requests old position
-> LOCK_POSITION denies Undo
```

The history entry remains available rather than silently bypassing the lock.

## 8. Text editing

Display mode belongs to Pixi. Edit mode belongs to DOM overlay UI.

`CanvasTextEditSession` provides:

- composition start/end boundary;
- no `SET_TEXT` while Chinese/Japanese/Korean IME composition is incomplete;
- normalized line breaks on paste;
- NUL stripping;
- Unicode grapheme counting via `Intl.Segmenter` with fallback;
- commit as NODE-38 `SET_TEXT` operation.

Keyboard command handling explicitly ignores input, textarea and contenteditable targets.

## 9. Assets and GPU lifecycle

Asset identity is separate from texture identity.

```text
asset_id
 -> CanvasAssetResolver authorization
 -> thumbnail / preview / full resolved URL
 -> loader / texture
 -> ProgressiveAssetCache
```

The resource manager provides:

- deduplicated in-flight load;
- tiered cache identity;
- reference count;
- byte budget;
- LRU eviction for unreferenced entries;
- explicit loader destroy on disposal;
- cross-project clipboard asset remapping/revalidation.

Pixi handles and URLs are never stored in Design IR.

## 10. Clipboard

Clipboard format:

```text
lumi-design-ir-fragment-v1
```

It serializes a selected IR subtree, not renderer objects. Runtime/Pixi/ephemeral metadata is stripped. Paste allocates collision-safe node IDs, rebuilds hierarchy, offsets fragment roots, and asks `ClipboardAssetPolicy` to map asset IDs for the destination document/project.

## 11. Renderer adapter

`PixiV8RendererAdapter` owns runtime entries keyed by node id and render key. Sync is incremental:

- create missing display;
- update dirty display only;
- reparent renderer object when scene hierarchy changes;
- hide offscreen nodes;
- destroy removed renderer objects;
- apply camera to the Pixi stage.

`createPixiV8Bindings()` maps the renderer-neutral operations to PixiJS v8 Container/Text/Graphics/Sprite/Matrix APIs. LUMI renderer IDs are attached as non-enumerable runtime properties and never become DesignDocument fields.

## 12. Browser integration gate

`/canvas-engine` is the NODE-40 integration harness. It uses the same Pixi CDN baseline already established by NODE-08, but its document and edit flow use the production `CanvasController`.

Playwright `apps/web/e2e/canvas-engine.spec.ts` verifies:

1. a real Pixi canvas becomes ready;
2. an unlocked move commits and increments Design IR version;
3. a HARD `LOCK_POSITION` rejects a subsequent move and leaves the version/document unchanged;
4. camera pan changes view state without a node transform rewrite.

NODE-08 browser tests remain as broader renderer/IME/stress regression evidence.

## 13. Performance contract

NODE-08 proved the renderer choice using synchronous Pixi workloads and recorded:

```text
2k scene P95  = 6.5 ms
10k scene P95 = 4.9 ms
```

Its headless rAF control was approximately 50 ms / ~20 fps, so hosted headless rAF cannot certify workstation 60 fps.

NODE-40 therefore freezes a **16.7 ms synchronous frame-work budget** for deterministic culling/spatial workload regression. `runtime-performance.test.ts` runs both 2,000-node and 10,000-node mixed scenes.

This gate is not a claim that GitHub hosted Chromium delivers 60 fps. Representative Windows/macOS GPU hardware certification remains a later performance/scalability gate.

## 14. Failure policy

- Hard constraint deny: rollback to original document.
- Stale document version: no commit.
- Missing asset: placeholder / revalidation, never corrupt IR.
- Missing renderer node: recreate from scene snapshot.
- Malformed IR node: diagnostic + isolate.
- GPU resource no longer referenced: release/destroy.
- Renderer failure must never mutate persisted document as a recovery strategy.

## 15. Acceptance commands

```bash
python scripts/validate_canvas_engine.py
pnpm --filter @lumi/canvas-sdk typecheck
pnpm --filter @lumi/canvas-sdk test
pnpm exec playwright test apps/web/e2e/canvas-engine.spec.ts
pnpm --filter @lumi/canvas-sdk exec vitest run src/runtime-performance.test.ts
```

NODE-40 remains `IMPLEMENTED / VALIDATING / not COMPLETE` until hosted contract, quality, browser E2E and benchmark jobs actually execute green.

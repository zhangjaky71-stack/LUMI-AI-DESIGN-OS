# Canvas Engine V1 — NODE-40

## Status

`IMPLEMENTED / VALIDATING`

NODE-40 implements the renderer-neutral Canvas interaction runtime on top of NODE-38 Design IR and accepts a NODE-39 constraint preflight at the operation gateway. Canvas is a view/interaction runtime; Design IR remains the source of truth.

## Runtime boundary

```text
React chrome / DOM overlays
        |
        v
CanvasController
|- CanvasCamera
|- SelectionModel
|- TransformSession
|- Snapping
|- CanvasCommandHistory
|- CanvasResourceManager
|- SpatialIndex / culling
|- Clipboard / keyboard
|- RendererAdapter
|    |- HeadlessRendererAdapter
|    `- PixiV8RendererAdapter (bindings injected by browser host)
        |
        v
NODE-38 applyOperation/applyBatch
        |
        +-- NODE-39 ConstraintPreflight
```

The domain/controller layer never imports Pixi classes. `PixiV8RendererAdapter` accepts opaque browser-owned bindings and translates renderer-neutral snapshots into an imperative scene graph. No Pixi object may be written into Design IR.

## Camera and coordinate model

`CanvasCamera` keeps viewport state separate from Design IR:

- world -> screen and screen -> world round trips;
- zoom-to-cursor anchor preservation;
- screen-space pan;
- fit-all / fit-selection bounds;
- zoom clamp;
- CSS viewport plus DPR state;
- world viewport rectangle for culling.

Camera changes never emit Design IR operations.

## Scene projection and fault isolation

`buildScene()` projects supported NODE-38 node kinds into immutable `RenderNodeSnapshot` records:

- FRAME
- GROUP
- TEXT
- IMAGE
- SHAPE
- VECTOR_PATH
- VIDEO
- MASK
- GUIDE
- COMPONENT
- INSTANCE

Malformed geometry or unsupported custom nodes become renderer placeholders plus diagnostics instead of crashing the whole canvas. Missing references and orphan nodes are isolated and reported.

## Selection

Selection supports:

- click hit-test;
- shift selection;
- marquee selection;
- layer/select-through cycling;
- group isolation boundary;
- locked nodes remain selectable but are excluded from transformable targets.

`SpatialIndex` owns viewport/hit queries. V1 uses a deterministic renderer-neutral index implementation; its API permits replacement with a production R-tree/bucket index without changing controller behavior.

## Transform transaction

Pointer interaction uses local preview state only.

```text
pointer down
-> TransformSession captures original geometry
-> pointer move updates local preview
-> pointer up materializes MOVE_NODE / RESIZE_NODE / ROTATE_NODE
-> CanvasOperationGateway calls NODE-38 applyBatch
-> NODE-39 preflight runs before commit
-> accepted: Design IR advances
-> denied: document is unchanged and preview resets to original geometry
```

Locked nodes are rejected before a transform session can start. Multi-node move is supported in one Design IR batch; V1 resize/rotate are single-target sessions to avoid ambiguous group geometry semantics.

## Snapping

V1 snapping evaluates world-space edge/center anchors against:

- nearby nodes / frames;
- configurable grid;
- screen-pixel threshold normalized by camera zoom.

Guides are returned as transient interaction data and are not persisted.

## Text editing

`TextEditSession` is the DOM-overlay state contract. It supports:

- composition start/update/end;
- commit prohibition while IME composition is active;
- Unicode grapheme segmentation via `Intl.Segmenter` when available;
- line breaks;
- plain-text paste sanitization;
- normalized-rich paste with script/style/event/javascript stripping;
- final `SET_TEXT` operation descriptor.

A real browser DOM editor is deliberately host-owned so Canvas core can be unit-tested without a browser.

## Resource manager

`CanvasResourceManager` enforces:

```text
asset_id
-> authorized AssetResolver
-> preview/full URL
-> TextureLoader
-> ref-counted LRU entry
-> destroy() on eviction / canvas teardown
```

The canvas never treats a pasted or persisted external URL as an authorized asset source. Cross-project clipboard operations call `ClipboardAssetPolicy.remapAsset()`.

## Renderer adapters

`HeadlessRendererAdapter` supports deterministic tests.

`PixiV8RendererAdapter` is the production adapter boundary. The repository's current frozen lock does not contain `pixi.js`; NODE-40 therefore does not silently mutate the lock or use an unpinned CDN. Browser host bindings must provide PixiJS v8 lifecycle methods: mount, camera, node sync/remove, selection, render, destroy.

This preserves the NODE-08 PixiJS v8 architectural decision while keeping dependency installation reproducible. Actual pinned Pixi bundle wiring is tracked as a production gap, not claimed complete.

## Command history

`CanvasCommandHistory` is separate from Artifact/Design version history. It stores forward/inverse operation descriptors and replays them through `CanvasOperationGateway`, so undo/redo still encounters version and constraint checks. Drag commands can coalesce by key.

## Clipboard and keyboard

Internal copy uses `lumi.canvas-fragment/1.0` and includes selected subtrees. Cross-project assets must be remapped through policy.

P0 keyboard mapping includes V, Space, Delete/Backspace, copy/paste, undo/redo and arrow nudge. Input, textarea, select and contenteditable targets are ignored.

## Scheduling and culling

`CanvasController` batches render requests through an injectable frame scheduler. Production hosts use `RafFrameScheduler`; tests use `ImmediateFrameScheduler`. Viewport queries return only visible/overscan nodes; pointer move can remain in the imperative interaction layer instead of React global state.

## Validation evidence

Local isolated evidence on the exact NODE-40 candidate source:

- TypeScript strict compile: PASS (local TypeScript 5.8.3 with repository-equivalent strict options)
- TypeScript test-suite strict compile: PASS
- headless runtime smoke: PASS
- structural benchmark reference:
  - 2,000 nodes: build ~= 5.42 ms, viewport query ~= 0.18 ms
  - 10,000 nodes: build ~= 15.31 ms, viewport query ~= 0.54 ms

These timings are diagnostic CPU structural measurements only. They are **not** browser FPS, GPU memory or NODE-08 standard-machine release evidence.

## Production gaps

See `reports/nodes/NODE-40/gap-ledger.json` for the authoritative gap list. V1 does not claim browser Pixi bundle execution, browser IME/pinch E2E, GPU texture telemetry, standard-machine FPS budget or Safari validation until those gates run.

## Next node

NODE-41 — Canvas Compiler.

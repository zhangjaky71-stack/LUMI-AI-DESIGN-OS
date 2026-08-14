# NODE-40 — Canvas Engine Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-40-canvas-engine`  
> Base: `node-39-constraint-validator-release`

## Scope evidence

| Requirement | Evidence | State |
| --- | --- | --- |
| Design IR is source of truth | `packages/canvas-sdk/src/ir-scene.ts` | IMPLEMENTED |
| No second canvas document protocol | production scene projects NODE-38 `DesignDocument` | IMPLEMENTED |
| Pixi runtime is renderer-only | `renderer.ts`, `pixi-v8-bindings.ts` | IMPLEMENTED |
| Infinite camera | `camera.ts`, `controller.ts` | IMPLEMENTED |
| Camera applied to real Pixi stage | renderer `setCamera` + Pixi matrix binding | IMPLEMENTED |
| World/screen conversion | `camera.ts` + camera tests | IMPLEMENTED |
| High-DPI boundary | `physicalCanvasSize`, renderer resize contract | IMPLEMENTED |
| Nested affine transforms | `matrix.ts`, `ir-scene.ts` | IMPLEMENTED |
| `rotation_deg` semantics | matrix/geometry compatibility fix | IMPLEMENTED |
| Multi-frame scene | `frame_ids`, fit frame/all | IMPLEMENTED |
| Ancestor visibility inheritance | scene projection + runtime regression | IMPLEMENTED |
| Ancestor lock inheritance | scene projection + runtime regression | IMPLEMENTED |
| Spatial culling/index | `spatial-index.ts` | IMPLEMENTED |
| Visible ancestor closure during culling | `CanvasController.renderNow()` | IMPLEMENTED |
| Topmost hit test/select-through | spatial + selection tests | IMPLEMENTED |
| Multi-select/marquee | `selection.ts` | IMPLEMENTED |
| Locked nodes selectable but not transformable | selection/runtime tests | IMPLEMENTED |
| Group isolation | `selection.ts` ancestry gate | IMPLEMENTED |
| Snapping | `snapping.ts`, camera-snapping tests | IMPLEMENTED |
| Local drag/resize/rotate preview | `transform-session.ts` | IMPLEMENTED |
| Pointer-up DesignOperation commit | transform/controller | IMPLEMENTED |
| NODE-39 hard constraint rollback | runtime test + browser E2E | IMPLEMENTED |
| Constraint-aware undo/redo | `command-bus.ts` + tests | IMPLEMENTED |
| DOM/IME-safe text contract | `text-edit.ts` + tests | IMPLEMENTED |
| Grapheme-aware text | `Intl.Segmenter` test | IMPLEMENTED |
| Authorized asset resolver | `resource-manager.ts` | IMPLEMENTED |
| Progressive cache/reference lifecycle | resource/asset-cache tests | IMPLEMENTED |
| Concurrent shared-texture ref counting | resource manager + asset residency tests | IMPLEMENTED |
| Viewport/zoom-driven asset residency | `asset-residency.ts`, controller | IMPLEMENTED |
| Live texture lookup after LRU eviction | ResourceManager `peek()` only | IMPLEMENTED |
| Async asset race invalidation | request-token residency guard | IMPLEMENTED |
| GPU object cleanup | loader destroy + renderer disposal | IMPLEMENTED |
| Clipboard IR fragment | `clipboard.ts` | IMPLEMENTED |
| Cross-project asset revalidation | clipboard asset policy | IMPLEMENTED |
| Runtime/Pixi metadata stripping | clipboard test | IMPLEMENTED |
| Keyboard P0 map | `keyboard.ts` | IMPLEMENTED |
| Accessibility equivalent layers data | `selection.accessibleRows()` | IMPLEMENTED |
| Malformed node isolation | scene diagnostics + test | IMPLEMENTED |
| Incremental dirty render | render key + renderer test | IMPLEMENTED |
| Resized FRAME/SHAPE redraw | `redrawShape` binding + test | IMPLEMENTED |
| IMAGE/VIDEO display sizing | `setDisplaySize` binding | IMPLEMENTED |
| Renderer removal without double-disposal | reverse removal + `children:false` | IMPLEMENTED |
| RAF batching | `CanvasController.scheduleRender()` | IMPLEMENTED |
| Real PixiJS browser integration | `/canvas-engine` | IMPLEMENTED |
| Browser interaction E2E | `apps/web/e2e/canvas-engine.spec.ts` | IMPLEMENTED; hosted execution pending |
| 2k runtime performance gate | `runtime-performance.test.ts` | IMPLEMENTED; hosted measurement pending |
| 10k stress performance gate | same | IMPLEMENTED; hosted measurement pending |
| Frozen 16.7ms synchronous budget | `runtime-benchmark.ts` | IMPLEMENTED |
| Architecture validator | `scripts/validate_canvas_engine.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/canvas-engine.yml` | IMPLEMENTED; hosted execution pending |

## Runtime boundary

Persisted state:

```text
DesignDocument
DesignOperation
Constraint
Artifact/Version references
```

Disposable runtime state:

```text
CanvasSceneSnapshot
SpatialIndex
Selection
Camera
Pixi Container/Graphics/Text/Sprite
textures / GPU handles
interaction previews
```

No Pixi object is written into Design IR.

## Constraint acceptance

The production transform path is:

```text
CanvasTransformSession preview
-> DesignOperation[]
-> NODE-39 guardedExecute
-> ALLOW: update document + rebuild scene
-> DENY: keep original document + redraw original scene
```

Undo and redo replay operations through the same validator. A newly active hard lock can therefore deny Undo.

## Asset residency acceptance

Viewport culling drives `CanvasAssetResidency`, which chooses `thumbnail`, `preview`, or `full` from zoom and requests the resource through the authorized `CanvasAssetResolver` boundary. Concurrent callers share one load while retaining independent references. Async completions use per-node request tokens so an obsolete request cannot revive an offscreen or superseded resource.

`textureForAsset()` reads only `CanvasResourceManager.peek()` results. It does not keep a second stale texture map, so an LRU-evicted/destroyed GPU resource cannot remain reachable through the residency layer.

## Browser integration acceptance

`/canvas-engine` initializes a real PixiJS v8 Application through the production `PixiV8RendererAdapter` and `CanvasController`.

The Playwright gate verifies:

1. real canvas ready;
2. shape move succeeds;
3. Design IR document version increments;
4. later HARD `LOCK_POSITION` rejects a move;
5. rejected move leaves shape geometry and document version unchanged;
6. camera pan changes camera state independently.

The broader NODE-08 Pixi/IME/stress E2E remains available as regression evidence.

## Performance policy

NODE-08 synchronous renderer evidence established P95 6.5ms at 2k and 4.9ms at 10k for the technology-spike workload. NODE-40 freezes 16.7ms as the synchronous frame-work budget and adds a mixed Design IR scene/spatial-culling benchmark.

Hosted headless requestAnimationFrame timing is not used to claim workstation 60fps. Real Windows/macOS GPU certification remains a representative-hardware gate.

## Tests present

- `canvas-spike.test.ts` — NODE-08 compatibility regression.
- `runtime.test.ts` — IR projection, inherited visibility/locking, selection, constrained transforms.
- `command-bus.test.ts` — undo/redo and lock enforcement.
- `text-resource.test.ts` — IME, graphemes, resource lifecycle, clipboard.
- `asset-residency.test.ts` — shared in-flight references and zoom-tier residency.
- `renderer.test.ts` — dirty rendering, camera bridge, resize redraw/disposal.
- `camera-snapping.test.ts` — DPR, camera roundtrip, snapping.
- `diagnostics.test.ts` — malformed IR isolation.
- `runtime-performance.test.ts` — 2k/10k synchronous budget.
- `apps/web/e2e/canvas-engine.spec.ts` — real Pixi production browser gate.

## Acceptance gates before COMPLETE

1. Hosted `canvas-contract` executes green.
2. Hosted `canvas-quality` executes Canvas SDK tests and web lint green.
3. Hosted `canvas-browser-e2e` executes real Chromium/Pixi interaction green.
4. Hosted `canvas-benchmark` records 2k and 10k P95 within 16.7ms.
5. No Design IR / Constraint contract drift.
6. No persisted Pixi runtime object.
7. Release PR stays stack-compatible with `node-39-constraint-validator-release`.

## Current disposition

Implementation, real browser harness, tests, performance harness, architecture validator, runtime documentation and CI definitions are present. NODE-40 is intentionally **not COMPLETE** until the hosted gates actually execute successfully. If the GitHub account billing/spending-limit condition prevents jobs from starting, it must be recorded as an external CI blocker rather than a code failure.

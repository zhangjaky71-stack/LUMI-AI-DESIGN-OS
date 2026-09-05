# NODE-40 — Canvas Engine Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-40-canvas-engine`  
> Release base: `node-39-constraint-validator-release`

## Implemented evidence

| Area | Evidence | State |
| --- | --- | --- |
| Design IR source of truth | `ir-scene.ts`, NODE-38 types/operations | IMPLEMENTED |
| Renderer-only Pixi runtime | `renderer.ts`, `pixi-v8-bindings.ts` | IMPLEMENTED |
| Infinite camera + DPR | `camera.ts`, `controller.ts` | IMPLEMENTED |
| Nested affine / `rotation_deg` | `matrix.ts`, geometry regression | IMPLEMENTED |
| Multi-frame scene | `frame_ids`, fit frame/all | IMPLEMENTED |
| Inherited visibility/locking | `ir-scene.ts`, `runtime.test.ts` | IMPLEMENTED |
| Spatial culling + ancestor closure | `spatial-index.ts`, controller | IMPLEMENTED |
| Hit test / select-through / marquee / isolation | `selection.ts` | IMPLEMENTED |
| Snapping | `snapping.ts`, camera/snapping tests | IMPLEMENTED |
| Local move/resize/rotate preview | `transform-session.ts` | IMPLEMENTED |
| NODE-39 guarded pointer-up commit | transform/controller | IMPLEMENTED |
| Hard-lock rollback | runtime test + browser E2E | IMPLEMENTED |
| Constraint-aware undo/redo | `command-bus.ts` + tests | IMPLEMENTED |
| IME-safe DOM text editing | `text-edit.ts` + tests | IMPLEMENTED |
| Design IR clipboard | `clipboard.ts` | IMPLEMENTED |
| Cross-project asset revalidation | clipboard asset policy | IMPLEMENTED |
| Authorized resource manager | `resource-manager.ts` | IMPLEMENTED |
| Shared in-flight texture refs | resource + residency tests | IMPLEMENTED |
| Zoom/viewport asset residency | `asset-residency.ts`, controller | IMPLEMENTED |
| Live-only texture lookup after LRU | `ResourceManager.peek()` | IMPLEMENTED |
| Race-safe async asset invalidation | per-node request tokens | IMPLEMENTED |
| Incremental dirty renderer | render key + renderer tests | IMPLEMENTED |
| Shape resize redraw | `redrawShape` | IMPLEMENTED |
| Image/video display sizing | `setDisplaySize` | IMPLEMENTED |
| Safe renderer/GPU disposal | reverse removal + non-recursive destroy | IMPLEMENTED |
| RAF batching | `scheduleRender()` | IMPLEMENTED |
| Real Pixi browser harness | `/canvas-engine` | IMPLEMENTED |
| Real browser interaction E2E | `apps/web/e2e/canvas-engine.spec.ts` | IMPLEMENTED; hosted execution blocked |
| 2k + 10k perf gate | `runtime-performance.test.ts` | IMPLEMENTED; hosted execution blocked |
| 16.7ms synchronous budget | `runtime-benchmark.ts` | IMPLEMENTED |
| Static architecture guard | `scripts/validate_canvas_engine.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/canvas-engine.yml` | IMPLEMENTED |

## Runtime boundary

Persisted state is `DesignDocument` + `DesignOperation` + Constraint/Artifact references. `CanvasSceneSnapshot`, camera, selection, spatial indexes, Pixi objects, textures, GPU handles and interaction previews are disposable runtime state. No Pixi object is written into Design IR.

The production mutation path is:

```text
CanvasTransformSession preview
-> DesignOperation[]
-> NODE-39 guardedExecute
-> ALLOW: authoritative document + scene rebuild
-> DENY: original document remains authoritative
```

Undo/redo replay operations through the same constraint validator, so a newly active hard lock can deny Undo rather than being bypassed by snapshot restore.

## Asset residency

Viewport culling drives `CanvasAssetResidency`. Zoom chooses `thumbnail`, `preview` or `full`; loads cross the authorized `CanvasAssetResolver` boundary. Concurrent consumers share one in-flight load while retaining independent reference counts. Async completion is protected by per-node request tokens. `textureForAsset()` reads only live `CanvasResourceManager.peek()` entries, so LRU-evicted/destroyed resources are not retained through a stale second map.

## Browser integration

`/canvas-engine` uses the production `CanvasController` + `PixiV8RendererAdapter`. The Playwright gate verifies a real Pixi canvas, an accepted move with Design IR version increment, a later HARD `LOCK_POSITION` rejection that preserves geometry/version, and independent camera pan.

## Performance policy

NODE-08 recorded synchronous renderer P95 6.5ms at 2k and 4.9ms at 10k for the spike workload. NODE-40 freezes a **16.7ms synchronous frame-work budget** and adds a mixed Design IR scene/spatial-culling regression at 2k and 10k. Hosted headless rAF is not used to claim workstation 60fps.

## Hosted CI evidence

Initial release head: `ce3ce9c4bc34b13dd1e806c74b6a914c8a9d60b0`  
Canvas Engine workflow run: `31786212548`

Observed jobs:

```text
canvas-contract     failure (no steps executed)
canvas-quality      skipped
canvas-browser-e2e  skipped
canvas-benchmark    skipped
```

GitHub check annotation for `canvas-contract`:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

This is an **external GitHub Actions account/billing blocker**. No NODE-40 contract, typecheck, unit test, browser E2E or benchmark step executed in this run, so it is not evidence of a code/test failure and it is not evidence of a pass.

## Gates before COMPLETE

1. Hosted `canvas-contract` executes green.
2. Hosted `canvas-quality` executes Canvas SDK tests and web lint green.
3. Hosted `canvas-browser-e2e` executes real Chromium/Pixi interaction green.
4. Hosted `canvas-benchmark` records 2k/10k P95 within 16.7ms.
5. No Design IR / Constraint contract drift.
6. No persisted Pixi runtime objects.
7. Release PR remains stack-compatible with `node-39-constraint-validator-release`.

## Current disposition

**NODE-40 = IMPLEMENTED / VALIDATING / not COMPLETE.**

Implementation and validation harnesses are present. Completion is intentionally withheld until hosted gates actually execute successfully.

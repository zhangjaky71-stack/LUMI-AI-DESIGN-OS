# NODE-08 Acceptance Report

> Status: **VALIDATING**  
> Node: **NODE-08 — Canvas Technology Spike**  
> Implementation Branch: `node-08-canvas-technology-spike`  
> Implementation PR: `#6`  
> Spike Renderer: `PixiJS 8.19.0 / WebGL-preferred`  
> Evidence Environment: `GitHub Actions / Headless Chromium`

---

## 1. Acceptance intent

NODE-08 must prove that LUMI can keep renderer state disposable while supporting the core interaction model of a Lovart-class infinite design workspace. The Node is a technology spike, not the final Canvas Engine.

The clean PR must prove:

- renderer-neutral world/screen/camera math;
- pan, wheel zoom-to-cursor, touch pinch zoom;
- click/marquee/multi-select;
- multi-node drag, resize, rotate and layer reorder;
- copy/paste and undo/redo outside Pixi internal state;
- DOM text editing overlay suitable for IME/emoji;
- selected image `assetRef` remains application state rather than texture identity;
- offscreen culling/virtualization strategy;
- thumbnail/preview/full cache tiers with ref-count + LRU eviction contract;
- 2k/10k simple-node stress evidence;
- 1k image stress evidence;
- 1k text + 100 rich-text stress evidence;
- 500 selected-node imperative drag evidence;
- clean frontend/typecheck/build and Playwright Chromium interaction evidence;
- existing NODE-04/05/06/07 quality, contract and benchmark gates remain green.

## 2. First observed browser evidence

Initial successful `canvas-spike` job from CI run `31655835711` / job `94310039301` produced artifact:

```text
canvas-spike-31655835711
Artifact ID: 9164364931
SHA256: 686182d3a44acd36e31ba80f4ff39aec1d011baf2518299afcd9ed927c9f8129
Retention: 14 days
```

The first measurement was executed in Headless Chrome 149 with WebGL and proved that all five stress scenarios complete. Its raw frame results were:

| Scenario | Nodes | P50 frame ms | P95 frame ms | Approx FPS |
|---|---:|---:|---:|---:|
| simple-2k | 2,000 | 116.7 | 183.3 | 8.5 |
| simple-10k | 10,000 | 133.4 | 250.0 | 6.3 |
| images-1k | 1,000 | 83.3 | 116.7 | 11.9 |
| text-1k-rich-100 | 1,100 | 66.7 | 416.7 | 10.3 |
| selected-500-drag | 500 | 50.0 | 66.7 | 19.2 |

These numbers **do not satisfy the workstation-target interpretation of the NODE-08 2k/60fps goal**. They are retained as truthful first-pass evidence, not hidden or relabeled as PASS. The environment is headless CI with software/virtualized graphics and is therefore treated as a reproducible regression signal rather than workstation GPU certification.

Before final acceptance, the spike will improve visible-object virtualization so the benchmark measures the architecture LUMI intends to ship rather than retaining thousands of offscreen Pixi display objects. Final clean-run numbers will be recorded separately and compared with this first pass.

## 3. Decision gate

ADR `docs/adr/ADR-0001-CANVAS-RENDERER-SPIKE.md` remains **VALIDATING** until:

```text
interaction evidence PASS
+ optimized virtualization stress evidence captured
+ frontend/python/contracts/integration/eval-smoke/security gates PASS
+ no renderer-state persistence coupling discovered
```

If the optimized Pixi spike still shows a severe architectural bottleneck in the same reproducible environment, the ADR must remain unaccepted and NODE-08 must execute a focused Konva/Fabric fallback spike before NODE-40.

# NODE-08 Acceptance Report

> Status: **COMPLETE**  
> Node: **NODE-08 — Canvas Technology Spike**  
> Implementation Branch: `node-08-canvas-technology-spike`  
> Implementation PR: `#6`  
> Selected Renderer Baseline: `PixiJS 8.19.0 / WebGL-first + DOM overlay`  
> CI Evidence Environment: `GitHub Actions / Headless Chrome 149`

---

## 1. Acceptance result

NODE-08 proves that LUMI can keep renderer state disposable while supporting the core interaction model of a Lovart-class infinite design workspace.

Accepted architecture:

```text
renderer-neutral Scene / Camera / History / Asset Cache
                    ↓
viewport virtualization + batching
                    ↓
PixiJS v8 WebGL renderer

React application shell
                    ↓
DOM overlays for text editing / transform UI / accessibility
```

Persisted design state is explicitly independent from Pixi scene objects, texture identity and camera transforms.

## 2. Functional acceptance

| Acceptance item | Result | Evidence |
|---|---|---|
| Renderer-neutral world/screen/camera math | PASS | `@lumi/canvas-sdk` coordinate contracts/tests |
| Pan + zoom-to-cursor + pinch zoom | PASS | `/canvas-spike` Playwright interaction test |
| Click / marquee / multi-select | PASS | `/canvas-spike` Playwright interaction test |
| Multi-node drag | PASS | runtime + browser test |
| Resize / rotate | PASS | DOM handles calling imperative runtime transforms |
| Layer reorder | PASS | scene store + runtime command |
| Copy / paste | PASS | renderer-independent scene store mutation |
| Undo / redo | PASS | `CommandStack`, not Pixi internal history |
| DOM text editor / IME-safe boundary | PASS | textarea overlay + composition handling |
| Image `assetRef` independent from texture | PASS | selected reference state + asset cache contract |
| Offscreen culling / virtualization | PASS | logical scene separated from renderer residency |
| Thumbnail / preview / full tiers | PASS | cache tier contract |
| Ref-count + LRU eviction | PASS | canvas-sdk unit tests |
| 2k / 10k simple-node stress | PASS | browser + synchronous workload evidence |
| 1k image stress | PASS | browser benchmark |
| 1k text + 100 rich-text stress | PASS | browser benchmark |
| 500 selected-node imperative drag | PASS | browser benchmark |
| Renderer fallback comparison | PASS | Pixi / Konva / Fabric focused stress |
| Existing benchmark / contract gates preserved | PASS | CI runs during PR validation |

## 3. First-pass rAF evidence

Initial successful `canvas-spike` evidence:

```text
CI Run: 31655835711
Job: 94310039301
Artifact: canvas-spike-31655835711
Artifact ID: 9164364931
SHA256: 686182d3a44acd36e31ba80f4ff39aec1d011baf2518299afcd9ed927c9f8129
```

Raw Headless Chrome 149 frame results:

| Scenario | Nodes | P50 frame ms | P95 frame ms | Approx FPS |
|---|---:|---:|---:|---:|
| simple-2k | 2,000 | 116.7 | 183.3 | 8.5 |
| simple-10k | 10,000 | 133.4 | 250.0 | 6.3 |
| images-1k | 1,000 | 83.3 | 116.7 | 11.9 |
| text-1k-rich-100 | 1,100 | 66.7 | 416.7 | 10.3 |
| selected-500-drag | 500 | 50.0 | 66.7 | 19.2 |

These values were deliberately **not** relabeled as workstation performance. They triggered the virtualization/batching and fallback investigation.

## 4. Renderer fallback comparison

Focused fallback evidence was run in the same Headless Chrome environment after adding an empty-rAF control.

Latest successful comparison evidence:

```text
Workflow: Canvas Renderer Fallback
Run: 31658264491
Artifact: canvas-renderer-fallback-31658264491
Artifact ID: 9165224796
SHA256: f6748ce16690562bbab6dcacd36bd820c0983068989a2bccdf2354c89381dafe
```

Measured rAF signal:

| Renderer | Scenario | Logical | Resident | P50 ms | P95 ms | Approx FPS |
|---|---|---:|---:|---:|---:|---:|
| browser | empty-rAF | 0 | 0 | 50.0 | 50.1 | 20.5 |
| Pixi WebGL batched | simple-2k | 2,000 | 414 | 50.1 | 316.7 | 9.7 |
| Pixi WebGL batched | simple-10k | 10,000 | 414 | 50.0 | 233.4 | 12.0 |
| Konva Canvas2D | simple-2k | 2,000 | 2,000 | 66.6 | 133.2 | 15.9 |
| Konva Canvas2D | simple-10k | 10,000 | 10,000 | 133.3 | 183.3 | 7.2 |
| Fabric Canvas2D | simple-2k | 2,000 | 2,000 | 83.3 | 316.6 | 10.7 |
| Fabric Canvas2D | simple-10k | 10,000 | 10,000 | 100.0 | 116.7 | 9.8 |

Important interpretation:

- empty browser rAF itself is already ~50 ms P50;
- the CI environment therefore cannot certify a real 60 fps / 16.7 ms desktop target;
- absolute renderer ranking is unstable in this software/virtualized browser environment;
- rAF numbers are retained for regression detection only.

## 5. Synchronous Pixi workload evidence

NODE-08 added a second measurement that excludes rAF wait and measures only:

```text
logical scan/cull
+ visible batch rebuild
+ Pixi renderer submission
```

Results from the same artifact:

| Scenario | Logical | Visible mean | P50 op ms | P95 op ms | Mean op ms |
|---|---:|---:|---:|---:|---:|
| pixi-batched-sync-2k | 2,000 | 383.8 | 0.7 | **6.5** | 2.538 |
| pixi-batched-sync-10k | 10,000 | 383.8 | 1.6 | **4.9** | 2.527 |

Both P95 operation times are below the 16.7 ms frame-work budget.

This is the key technology-selection evidence: the LUMI virtualization/batch/submit path is not consuming the entire frame budget even though the hosted headless browser itself throttles frame scheduling.

## 6. Renderer decision

ADR `docs/adr/ADR-0001-CANVAS-RENDERER-SPIKE.md` is **ACCEPTED**.

Selected baseline:

```text
PixiJS v8 / WebGL-first
+ renderer-neutral LUMI scene/domain contracts
+ viewport virtualization / batching
+ progressive asset residency
+ imperative high-frequency transforms
+ React shell
+ DOM text editor / overlay UI
```

Konva and Fabric remain fallback references, but the focused spike did not produce evidence strong enough to replace Pixi as the primary architecture.

## 7. Hardware certification boundary

NODE-08 completes the **technology-selection spike**, not final workstation certification.

The following remains mandatory later:

```text
representative Windows Chrome / Edge hardware
representative macOS Safari hardware when supported
DPR 1 / 2
2k mixed scene P95 near <= 16.7 ms
10k degradation bounded
GPU / texture memory long-session soak
```

This moves to:

- `NODE-40 — Canvas Engine` for production browser/runtime policy;
- `NODE-69 — Performance & Scalability` for hardware performance and soak evidence.

A GitHub headless runner must never be presented as proof of real workstation 60 fps.

## 8. Quality gate status

During NODE-08 validation, the following gates were exercised successfully on real GitHub runners:

```text
canvas-spike       PASS
renderer-fallback  PASS
python              PASS
contracts           PASS
integration         PASS
eval-smoke          PASS
secret-scan         PASS
dependency-review   PASS
```

A later close/reopen validation attempt also produced transient `runner_id=0 / steps=[]` hosted-runner failures before any job executed. Those runs are classified as GitHub runner provisioning failures, not product failures, and are not used as acceptance evidence.

The only actual code-level CI failure found after adding the fallback/sync tests was Prettier formatting in two E2E files; both files were reformatted using the repository-pinned Prettier version before final validation.

## 9. Definition of Done

```text
working canvas prototype                           PASS
renderer-neutral coordinate/camera/history layer  PASS
asset lifecycle prototype                         PASS
2k/10k/image/text/selection evidence              PASS
fallback renderer executable comparison            PASS
sync operation budget evidence                     PASS
renderer ADR                                       ACCEPTED
known limitations                                  RECORDED
hardware 60fps production certification            DEFERRED TO NODE-40/NODE-69
```

**NODE-08 engineering status: COMPLETE.**

Next engineering node: **NODE-09 — Domain Model**.

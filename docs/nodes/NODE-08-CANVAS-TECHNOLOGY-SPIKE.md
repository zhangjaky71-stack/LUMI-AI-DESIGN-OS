# NODE-08 — Canvas Technology Spike

> Phase: 0 Benchmark Before Build  
> Status: **COMPLETE**  
> Priority: P0  
> Depends on: NODE-02, NODE-05, NODE-06  
> Produces: Canvas renderer 技术验证、性能报告、ADR、可保留 prototype  
> Acceptance: `reports/nodes/NODE-08/acceptance.md`  
> ADR: `docs/adr/ADR-0001-CANVAS-RENDERER-SPIKE.md`

---

## 1. 目标与完成结论

NODE-08 在正式实现 Canvas Engine 前验证渲染、交互、坐标、历史、资源生命周期和大场景策略是否能支撑 Lovart 类无限设计画布。

最终结论：

```text
ACCEPT PixiJS v8 / WebGL-first
+ renderer-neutral LUMI scene contracts
+ viewport virtualization / batching
+ progressive asset residency
+ imperative high-frequency transforms
+ React application shell
+ DOM text editing / overlay UI
```

关键边界已经由 prototype 证明：

```text
Pixi Container/Sprite != persisted Design IR
GPU texture identity   != Asset identity
Pixi internal state    != Undo/Redo history
Camera transform       != persisted per-node transform rewrite
```

## 2. 已实现 prototype

`@lumi/canvas-sdk` 承载 renderer-neutral 能力：

- world/screen/camera conversion；
- zoom-to-cursor；
- culling / selection geometry；
- scene store；
- command-stack undo/redo；
- thumbnail / preview / full asset tiers；
- ref-count；
- LRU eviction。

`/canvas-spike` 承载 PixiJS WebGL prototype：

- infinite pan；
- wheel zoom；
- pinch zoom；
- zoom-to-cursor；
- frame/image/text/shape；
- click selection；
- marquee multi-select；
- multi-node drag；
- four resize handles；
- rotation；
- layer reorder；
- copy/paste；
- undo/redo；
- DOM textarea text editor；
- IME composition boundary；
- selected image `assetRef` display；
- viewport culling / virtualization；
- batched large-shape stress path。

## 3. 坐标系统

明确三层：

```text
World coordinates
Canvas/renderer coordinates
Screen/DOM coordinates
```

统一转换 API：

```text
worldToScreen(point)
screenToWorld(point)
zoomAtScreenPoint(camera, point, zoom)
```

DOM editor、transform handles 和后续 context menu / selection toolbar 必须继续使用统一转换，不允许散落手算。

## 4. React Boundary

React 管：

```text
application chrome
panels
commands
selection metadata
inspector
DOM overlays
```

Pixi imperative runtime 管：

```text
viewport transform
renderer scene residency
high-frequency pointer transforms
batch rebuild
renderer submit
```

禁止把每个 pointermove 写入 React 全树状态并触发大规模 reconciliation。

## 5. Text Strategy

显示态：Pixi `Text` / 必要时 `HTMLText`。

编辑态：

```text
selected text
→ position DOM editor via worldToScreen
→ textarea/contenteditable edit
→ IME composition-safe commit
→ normalized text state
→ renderer refresh
```

## 6. Image / Asset Strategy

- Asset identity 独立于 texture identity；
- thumbnail / preview / full 分级；
- 进入视口再提升分辨率；
- renderer residency 受 viewport 控制；
- cache 具备 ref-count + LRU eviction；
- production NODE-40 继续实现真实 texture unload / memory instrumentation。

## 7. 性能证据

### 7.1 Headless rAF 不能认证 60fps

GitHub Actions Headless Chrome 149 的空 `requestAnimationFrame` 控制组已经约：

```text
P50 = 50.0 ms
P95 = 50.1 ms
≈ 20.5 fps
```

所以该环境不能作为中档开发机 60fps 认证工具。

### 7.2 Synchronous Pixi workload

为排除 rAF 节流，NODE-08 单独测量：

```text
logical scan/cull
+ visible batch rebuild
+ Pixi renderer submit
```

| Scenario | Logical | Visible mean | P50 op ms | P95 op ms | Mean op ms |
|---|---:|---:|---:|---:|---:|
| pixi-batched-sync-2k | 2,000 | 383.8 | 0.7 | **6.5** | 2.538 |
| pixi-batched-sync-10k | 10,000 | 383.8 | 1.6 | **4.9** | 2.527 |

两个 P95 均低于 16.7ms frame-work budget。

证据：

```text
Workflow Run: 31658264491
Artifact ID: 9165224796
SHA256: f6748ce16690562bbab6dcacd36bd820c0983068989a2bccdf2354c89381dafe
```

## 8. Renderer Comparison

已执行同一浏览器环境下的：

```text
Pixi WebGL batched
Konva Canvas2D
Fabric Canvas2D
empty-rAF control
```

绝对 rAF 排名在软件/虚拟化浏览器中不稳定，因此不以该排名切换 renderer。结合：

- renderer-neutral architecture fit；
- large-scene residency control；
- GPU-first media direction；
- synchronous workload budget；
- interaction prototype completeness；

最终 ADR 接受 PixiJS v8 主基线。

## 9. 测试与验收

- [x] coordinate round trip；
- [x] zoom-to-cursor anchor；
- [x] pan / wheel / pinch；
- [x] pointer hit / selection；
- [x] marquee multi-select；
- [x] drag / resize / rotate；
- [x] layer reorder；
- [x] copy / paste；
- [x] undo / redo；
- [x] DOM text edit / IME boundary；
- [x] asset reference separation；
- [x] cache tier / ref-count / LRU contract；
- [x] 2k / 10k stress evidence；
- [x] 1k image stress；
- [x] 1k text + 100 rich-text stress；
- [x] 500 selection drag stress；
- [x] Pixi / Konva / Fabric focused fallback comparison；
- [x] renderer 与 persisted data 解耦；
- [x] ADR 明确选型；
- [x] known limitations / hardware gate documented。

## 10. Hardware Browser Gate

NODE-08 是 renderer 技术选型，不伪造 workstation certification。

Production 前仍必须在后续 Node 完成：

```text
Windows Chrome / Edge representative hardware
macOS Safari representative hardware when supported
DPR 1 / 2
2k mixed scene interactive P95 near <= 16.7ms
10k bounded degradation
long-session GPU / texture memory soak
```

Owner：

- NODE-40 — production Canvas Engine；
- NODE-69 — Performance & Scalability。

## 11. Definition of Done

```text
working canvas prototype                      PASS
performance evidence                          PASS
renderer fallback executable comparison       PASS
renderer ADR                                  ACCEPTED
known limitations                             RECORDED
reusable coordinate/viewport/cache prototype  PASS
```

**NODE-08 COMPLETE。下一节点：NODE-09 — Domain Model。**

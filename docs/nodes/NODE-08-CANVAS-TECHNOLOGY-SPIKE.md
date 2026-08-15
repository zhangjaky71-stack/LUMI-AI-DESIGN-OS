# NODE-08 — Canvas Technology Spike

> Phase: 0 Benchmark Before Build  
> Status: **VALIDATING**  
> Implementation Status: **IMPLEMENTED / CI VALIDATION IN PROGRESS**  
> Implementation Branch: `feat/node-08-canvas-spike`  
> Acceptance Report: `reports/nodes/NODE-08/acceptance.md`  
> Implemented At: `2026-08-16`  
> Priority: P0  
> Depends on: NODE-02, NODE-05, NODE-06  
> Produces: Canvas renderer 技术验证、性能报告、ADR、可保留的 prototype

---

## 1. 目标

在正式实现 Canvas Engine 前验证渲染与交互技术是否能支撑 Lovart 类无限设计画布。Architecture V2 首选 **PixiJS v8 + DOM overlay**，但 NODE-08 必须用实际 prototype 证明，而不是只看文档。

PixiJS v8 提供 scene graph、WebGL/WebGPU renderer、interaction events、text/HTMLText 和 culling 等能力，适合作为高性能 renderer；复杂输入、textarea/contenteditable、辅助 UI 由 DOM overlay 承担。

## 2. 候选

### Primary

```text
PixiJS v8 renderer
+ custom viewport/camera
+ custom selection/transform layer
+ DOM text editing overlay
```

### Comparison baseline

- react-konva / Konva；
- Fabric.js。

比较目的不是做三个完整编辑器，而是验证 primary 不存在致命缺陷。

## 3. Spike 不是正式 Domain Model

禁止：

```text
Pixi Container/Sprite object
=
Design IR persisted object
```

prototype 使用 adapter：

```text
SpikeNode JSON
   ↓
Renderer Adapter
   ↓
Pixi Scene Graph
```

以证明后续 Design IR 与 renderer 可以解耦。

## 4. 必做交互

prototype 至少：

- infinite pan；
- wheel/pinch zoom；
- zoom-to-cursor；
- frame；
- image node；
- text node；
- rect/vector placeholder；
- click selection；
- marquee multi-select；
- drag；
- resize handles；
- rotate；
- layer reorder；
- copy/paste；
- undo/redo prototype；
- offscreen culling；
- DOM text edit overlay；
- selected image reference 显示。

当前 branch 已实现以上 spike surface，最终 `COMPLETE` 仍以 CI 与浏览器 benchmark 验收为准。

## 5. 坐标系统

明确三层：

```text
World coordinates
Canvas/renderer coordinates
Screen/DOM coordinates
```

必须实现稳定转换 API：

```text
worldToScreen(point)
screenToWorld(point)
```

DOM text editor、context menu、selection toolbar 必须使用该转换，不允许散落手算。

当前实现集中在 `apps/web/public/canvas-spike/engine.mjs`，并有确定性 round-trip 与 zoom-anchor 测试。

## 6. Camera

Camera state：

```ts
interface CameraState {
  x: number
  y: number
  zoom: number
}
```

当前 spike benchmark bounds：

```text
MIN_ZOOM = 0.05
MAX_ZOOM = 8
```

Camera transform 只应用于 renderer world container，不写回每个 SpikeNode / future Design node。

## 7. 性能测试场景

### PERF-01 simple nodes

- 10,000 simple shapes；
- pan/zoom；
- visible culling。

目标：中档开发机交互 P95 frame time 尽可能保持 < 16.7ms；允许压力场景降级，但普通 2k scene 必须接近 60fps。

### PERF-02 images

- 1,000 image thumbnails；
- progressive loading；
- texture cache；
- offscreen unload/culling。

检查 GPU memory 不无限增长。

### PERF-03 text

- 1,000 text labels；
- 100 mixed rich text nodes；
- font switching。

### PERF-04 selection

500 selected nodes 进行 group drag，不能因每个 pointermove 触发 React 全树 re-render。

NODE-08 workflow 会在真实 Chromium 中执行 `mixed2k`、`simple10k`、`images1k`、`text1k` 与 `selection500`，把测量 JSON 上传为 Actions artifact；在 CI 完成前不提前填写伪造性能数字。

## 8. React Boundary

React 管：

```text
application chrome
panels
commands
selection metadata
inspector
DOM overlays
```

Pixi imperative layer 管高频 render/transform。

禁止把每帧 pointermove 全部写入 React server/client global state。

当前 spike 故意作为独立静态 prototype 运行，证明 renderer 可以完全通过 adapter 与应用/持久层解耦，而不是把 Pixi object 混进 React/domain state。

## 9. Text Strategy

显示态：Pixi `Text`/必要时 HTMLText。

编辑态：

```text
selected text
→ hide/ghost Pixi text
→ position DOM editor via worldToScreen
→ edit
→ commit normalized Text IR
→ rerender Pixi text
```

必须验证中文输入法 IME、emoji、换行、font loading。

当前 prototype 监听 `compositionstart` / `compositionend`，支持 CJK、emoji、多行输入，并由 Playwright 覆盖提交 + undo/redo；生产字体装载与排版精度仍属于后续 Canvas/Export 节点。

## 10. Image Strategy

- Object Storage URL 不直接永久作为 renderer source；通过 asset resolver。
- thumbnail/preview/full resolution 分级。
- 进入视口才加载高分辨率。
- texture cache 有 LRU/eviction 策略。

当前 spike 用 `asset://spike/...` reference + bounded `TexturePool` 模拟 asset resolver；离开视口释放引用，benchmark teardown 强制验证 texture pool 回到 0。

## 11. Browser Matrix

至少：

```text
Chrome current
Edge current
Safari current (可用 macOS CI/人工验证时)
```

目标桌面优先；移动端 P0 只要求可查看/基础操作，不承诺完整专业编辑。

自动 acceptance 当前在 Ubuntu Chromium 跑；Edge/Safari-specific host 验证保留为生产 Canvas browser matrix 的已知限制，不把未执行结果伪装为 PASS。

## 12. 比较决策

ADR：`docs/adr/0001-canvas-renderer-baseline.md`

| Criterion | Pixi | Konva | Fabric |
|---|---:|---:|---:|
| Large scene performance/headroom | 5 | 3 | 3 |
| Custom scene graph freedom | 5 | 4 | 4 |
| Native rich text editing | 3 | 3 | 5 |
| Interaction primitives | 3 | 5 | 5 |
| Export flexibility | 5 | 4 | 4 |
| React integration convenience | 3 | 5 | 3 |
| Low domain-model lock-in | 5 | 4 | 3 |

Architecture V2 只有在 Pixi 出现明确 blocker 时才修改 renderer baseline。当前 ADR 选择 **PixiJS v8 + DOM overlay**，Konva 为出现可复现 blocker 时的第一 fallback。

## 13. 测试

- coordinate round trip误差；
- zoom-to-cursor anchor；
- pointer interaction；
- selection transform；
- undo/redo command；
- IME/CJK/emoji/multiline；
- texture cleanup；
- resize/rotate；
- browser window resize；
- DPR aware renderer；
- 2k/10k stress recording。

确定性测试：

```bash
node --test apps/web/public/canvas-spike/engine.test.mjs
```

浏览器验收：

```bash
pnpm exec playwright test apps/web/e2e/canvas-spike.spec.ts
```

GitHub workflow：`.github/workflows/node-08-canvas-spike.yml`。

## 14. 验收标准

- [ ] Pixi prototype 可运行。
- [ ] infinite pan/zoom 可用。
- [ ] select/drag/resize/rotate 可用。
- [ ] DOM 中文文本编辑可用。
- [ ] 2k mixed nodes 常规操作有测量数据。
- [ ] 10k stress 有测量数据而非主观描述。
- [ ] memory/GPU resource 有释放验证。
- [ ] renderer 与 persisted data 解耦。
- [x] ADR 明确选型与 fallback。

其余项目将在 clean PR validation 通过后统一置为 `[x]`，不会在 CI 前提前宣称通过。

## 15. Definition of Done

```text
working canvas prototype
+ performance benchmark report
+ renderer ADR
+ known limitations
+ reusable coordinate/viewport prototype
+ clean repository CI
+ clean NODE-08 browser acceptance
```

完成 Phase 0 后，下一节点：NODE-09 Domain Model。

## 16. Implementation surface

当前 branch 已落地：

```text
apps/web/public/canvas-spike/
├─ index.html
├─ styles.css
├─ app.mjs
├─ engine.mjs
└─ engine.test.mjs

apps/web/e2e/canvas-spike.spec.ts
.github/workflows/node-08-canvas-spike.yml
docs/adr/0001-canvas-renderer-baseline.md
reports/nodes/NODE-08/acceptance.md
reports/nodes/NODE-08/known-limitations.md
```

NODE-08 当前处于 `VALIDATING`，不是 `COMPLETE`。完成状态只在所有 required acceptance evidence 真实通过后写回。

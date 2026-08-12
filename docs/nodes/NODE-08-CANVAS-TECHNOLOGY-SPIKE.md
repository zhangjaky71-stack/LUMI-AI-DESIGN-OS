# NODE-08 — Canvas Technology Spike

> Phase: 0 Benchmark Before Build  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
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

## 6. Camera

Camera state：

```ts
interface CameraState {
  x: number
  y: number
  zoom: number
}
```

约束：

```text
MIN_ZOOM = implementation benchmark result
MAX_ZOOM = implementation benchmark result
```

不要把 viewport transform 写回每个 Design node。

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

## 10. Image Strategy

- Object Storage URL 不直接永久作为 renderer source；通过 asset resolver。
- thumbnail/preview/full resolution 分级。
- 进入视口才加载高分辨率。
- texture cache 有 LRU/eviction 策略。

## 11. Browser Matrix

至少：

```text
Chrome current
Edge current
Safari current (可用 macOS CI/人工验证时)
```

目标桌面优先；移动端 P0 只要求可查看/基础操作，不承诺完整专业编辑。

## 12. 比较决策

ADR 记录：

| Criterion | Pixi | Konva | Fabric |
|---|---:|---:|---:|
| Large scene performance | | | |
| Custom scene graph freedom | | | |
| Text editing | | | |
| Interaction primitives | | | |
| Export flexibility | | | |
| React integration cost | | | |
| Long-term lock-in | | | |

Architecture V2 只有在 Pixi 出现明确 blocker 时才修改 renderer baseline。

## 13. 测试

- coordinate round trip误差；
- zoom-to-cursor anchor；
- pointer hit test；
- selection transform；
- undo/redo command；
- IME；
- texture cleanup；
- resize browser window；
- DPR 1/2；
- 10k stress recording。

## 14. 验收标准

- [ ] Pixi prototype 可运行。
- [ ] infinite pan/zoom 可用。
- [ ] select/drag/resize/rotate 可用。
- [ ] DOM 中文文本编辑可用。
- [ ] 2k mixed nodes 常规操作流畅。
- [ ] 10k stress 有测量数据而非主观描述。
- [ ] memory/GPU resource 有释放验证。
- [ ] renderer 与 persisted data 解耦。
- [ ] ADR 明确选型与 fallback。

## 15. Definition of Done

```text
working canvas prototype
+ performance benchmark report
+ renderer ADR
+ known limitations
+ reusable coordinate/viewport prototype
```

完成 Phase 0，下一节点：NODE-09 Domain Model。

# NODE-40 — Canvas Engine

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE UX  
> Depends on: NODE-08, NODE-38, NODE-39  
> Produces: PixiJS-based Infinite Canvas runtime、selection/transform/text/undo/culling/asset rendering

---

## 1. 目标

实现桌面优先的高性能无限设计画布，支持多 Frame、文本、图片、Shape/Vector、视频预览、选择与编辑。Canvas 是 Design IR 的可视化/交互 runtime，不是数据真相源。

## 2. Runtime Architecture

```text
React Application
├─ panels / toolbars / inspector
├─ command bus
└─ DOM overlays
       │
       ▼
Canvas Controller
├─ Camera
├─ Selection
├─ Transform
├─ Snapping
├─ Clipboard
├─ Command History
├─ Resource Manager
└─ Renderer Adapter
       │
       ▼
PixiJS v8 Scene Graph
```

## 3. Camera / Infinite Space

支持：

- wheel/pinch zoom；
- pan middle mouse/space drag；
- zoom-to-cursor；
- fit frame/selection/all；
- world↔screen transform；
- high-DPI。

Camera 是 user view state，不写 Design IR node transform。

## 4. Rendering Nodes

V1：

```text
FRAME
GROUP
TEXT
IMAGE
SHAPE
VECTOR_PATH
VIDEO poster/preview
MASK
GUIDE
COMPONENT/INSTANCE basic
```

Renderer Adapter 决定 Pixi object；Domain 不 import Pixi types。

## 5. Selection

- click；
- shift multi-select；
- marquee；
- select through/layer cycling；
- locked nodes不可 transform；
- group enter/isolation；
- semantic node badges optional。

## 6. Transform

操作期间使用 local preview transform；pointer up 后提交 DesignOperation：

```text
MOVE_NODE
RESIZE_NODE
ROTATE_NODE
```

Constraint preflight fail 时恢复视觉状态并显示原因。

## 7. Snapping

V1：

- frame edges/center；
- nearby node edges/center；
- configurable grid；
- smart distance guides。

Snapping 在 canvas interaction 层计算，最终位置作为 operation payload。

## 8. Text Editing

显示态：Pixi text representation。

编辑态：DOM overlay，支持：

- 中文 IME；
- selection/caret；
- line breaks；
- emoji/graphemes；
- font loading；
- paste plain/rich policy。

commit 后生成 `SET_TEXT`/style ops。

## 9. Asset Resource Manager

```text
asset_id
→ authorized resolver
→ preview URL
→ texture cache
→ viewport-based high-res upgrade
```

LRU/eviction，离开视口/删除 node 后释放 GPU texture引用。

## 10. Culling / Performance

- spatial index；
- viewport culling；
- thumbnails；
- dirty-node incremental update；
- 不把 pointermove 写 React global state；
- requestAnimationFrame 合并更新。

目标以 NODE-08 实测基线设 CI/perf budget。

## 11. Clipboard

内部剪贴板使用 Design IR fragment；系统剪贴板可导出文本/图片，但导入要 sanitize。跨 Project paste 重新解析 asset access/复制 policy。

## 12. Undo / Redo

UI command history 与 persisted version history分开：

- interaction undo 可合并连续 drag；
-已保存重要 checkpoint 创建 Artifact/Design version；
- undo 仍经过 constraints/version conflict。

## 13. Keyboard

P0：

```text
V/Select
Space/Pan
Delete
Cmd/Ctrl+C/V
Cmd/Ctrl+Z/Shift+Z
Arrow nudge
Shift proportional resize
```

避免劫持输入框快捷键。

## 14. Error/Loading

缺资产、字体、损坏 node 不能让整 Canvas crash；渲染 placeholder + diagnostics。

## 15. Accessibility

Canvas 本身为视觉工具，但 UI controls必须 keyboard可达、ARIA label；选中节点可在 Layers/Inspector以 DOM 方式访问。

## 16. Tests

- world/screen math；
- selection/hit testing；
- constraints transform rollback；
- IME；
- multi-select；
- asset texture cleanup；
- 2k mixed normal perf；
- 10k stress；
- DPR/browser resize；
- malformed node isolation。

## 17. 验收标准

- [ ] Infinite pan/zoom 稳定。
- [ ] 多 Frame 可编辑。
- [ ] text/image/shape/vector 基础编辑。
- [ ] select/resize/rotate/group。
- [ ] 中文 IME。
- [ ] constraint enforcement 接入。
- [ ] culling/texture cleanup。
- [ ] 普通场景接近 60fps 基准。

## 18. Definition of Done

```text
production canvas runtime implemented
+ interaction E2E green
+ performance budget green
+ no persisted Pixi object
```

下一节点：NODE-41 Canvas Compiler。

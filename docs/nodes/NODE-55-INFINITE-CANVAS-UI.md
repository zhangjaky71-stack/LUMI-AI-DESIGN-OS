# NODE-55 — Infinite Canvas Product UI

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / LOVART-PARITY CORE  
> Depends on: NODE-40, NODE-41, NODE-54  
> Produces: Product-grade Infinite Canvas集成、多Frame、工具栏、导航/快捷键/拖放/性能体验

---

## 1. 目标

将 NODE-40 Canvas Engine真正嵌入用户工作流，形成ChatCanvas式体验。此Node关注产品交互和完整集成，而不是重复写renderer底层。

## 2. Canvas Surface

- infinite world；
-多Frame并排；
-自由放置reference/artifact；
- pan/zoom；
- fit/zoom controls；
- selection；
- grid/guides；
- dark/light workspace根据产品UI设置。

## 3. Top/Context Toolbar

根据selection显示：

```text
position/size
crop
fill/stroke
font basics
lock
arrange
mask
use as reference
AI edit
```

复杂属性进 Inspector。

## 4. Frame Creation

提供常用尺寸preset：

```text
1:1
4:5
9:16
16:9
A4/print optional
custom
```

Preset只是Frame dimension，不自动宣称适配已完成；跨尺寸重排调用Design Adaptation。

## 5. Drag & Drop

来源：

- Asset panel；
- Artifact card；
-系统文件；
-其他Frame/Canvas selection。

上传文件先走Asset lifecycle；未READY显示placeholder。

## 6. Context Menu

```text
copy/paste
duplicate
group/ungroup
lock/unlock
bring forward/back
use as reference
AI edit
create component optional
```

权限/constraint不允许的操作disable并解释。

## 7. Navigation

P0：

- minimap optional if性能可接受；
- frame navigator；
- command palette/search node P1；
- breadcrumbs group isolation。

## 8. Autosave

高频drag不每帧写DB。策略：

```text
local command buffer
→ debounce/interaction end
→ batch DesignOperations
→ server version
→ acknowledge
```

页面离开前flush/提示。Version conflict走明确rebase/reload。

## 9. Offline/Disconnect

P0不是完整offline editor，但网络断开：

-保留未提交local commands有限时段；
-明显offline badge；
-重连检查document version；
-冲突不静默覆盖。

## 10. AI Edit Gesture

选择node/region → “AI Edit” → composer自动带 selection context。对于raster可进入mask brush P1/基础版本；明确protected elements。

## 11. Performance UI

- 大图先preview；
-缩放低时简化效果；
-Frame outside viewport cull；
-加载高分图时不冻结交互。

## 12. Tests

- frame preset；
- drag/upload；
- autosave batching；
- version conflict；
- copy/paste；
- locked node menu；
- reconnect；
- 2k node user flow performance。

## 13. 验收标准

- [ ] 多Frame无限画布可用。
- [ ] Asset/Artifact可拖入。
- [ ] Canvas edit产生DesignOps并autosave。
- [ ] 版本冲突不覆盖。
- [ ] AI Edit携带精确selection。
- [ ] 常用专业快捷键可用。

## 14. Definition of Done

```text
infinite canvas product integration green
+ autosave/version E2E green
+ perf acceptance green
```

下一节点：NODE-56 Layers / Inspector。

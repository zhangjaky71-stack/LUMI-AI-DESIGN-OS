# NODE-41 — Canvas Compiler

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-38, NODE-40  
> Produces: Design IR → Scene Graph 编译器、增量 patch、资源解析、确定性 preview/render bridge

---

## 1. 目标

建立稳定编译边界，使 Canvas renderer 可以替换而不改变 Design IR。编译器把语义节点转换成 renderer-neutral scene representation，再由 Pixi adapter materialize。

## 2. Pipeline

```text
Design IR
→ validate
→ normalize defaults/tokens
→ resolve resources
→ layout/geometry normalization
→ SceneNode IR
→ Renderer Adapter
→ Pixi objects
```

## 3. SceneNode

只含渲染需要数据：

```text
id
kind
world_transform
clip/mask
resolved_style
resolved_text
resolved_resource
z_order
interaction_flags
```

不持久化。

## 4. Full Compile

用于：

- 首次打开；
- schema migration后；
- renderer恢复；
- export snapshot。

输出 compile diagnostics。

## 5. Incremental Compile

DesignOperation/SemanticDiff → dirty set：

```text
changed node
+ descendants if inherited/layout affected
+ mask/group dependencies
+ resource dependents
```

只 patch 受影响 scene nodes。

## 6. Resource Resolver

异步解析：

```text
asset_id → preview/full URL
font_asset_id → loaded font
brand_token_id → resolved style
video asset → poster/stream ref
```

resource missing时 placeholder，不把 presigned URL回写 IR。

## 7. Fonts

Font resolver以 family/style/asset id映射浏览器字体。字体 load 完成后触发相关 Text nodes remeasure/recompile。

跨浏览器字体 metrics差异需 snapshot tests + export server使用相同/受控字体资源。

## 8. Layout

V1 基础 group/frame constraints；高级 Auto Layout 未来扩展。任何 renderer convenience layout 不成为隐藏持久规则；可重现布局必须进入 IR/compiled deterministic rules。

## 9. Error Handling

单 node compile error：

```text
scene placeholder
+ diagnostic node id
```

全局 structural invalid：拒绝 compile。

## 10. Deterministic Preview

同 Design IR +同资源版本+同 compiler version 应得到等价 scene。记录 `compiler_version` 进入 Artifact provenance。

## 11. Compiler Version

升级影响视觉时必须：

- snapshot compare；
- benchmark old/new；
-历史 artifact保留 rendered file；
-必要时支持 old compiler image一段 retention period。

## 12. Tests

- fixture snapshots；
- incremental vs full compile等价；
- resource async load；
- font remeasure；
- mask/group；
- malformed node placeholder；
- missing asset；
- compiler version snapshot。

## 13. 验收标准

- [ ] Design IR 不依赖 Pixi。
- [ ] Full/Incremental compile。
- [ ] resource resolver授权化。
- [ ] incremental结果与full等价。
- [ ] compiler version进入 provenance。

## 14. Definition of Done

```text
compiler + Pixi adapter implemented
+ fixture snapshots green
+ incremental equivalence tests green
```

下一节点：NODE-42 Artifact Engine。

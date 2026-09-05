# NODE-41 — Canvas Compiler

> Phase: 5 Design Intelligence  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / CORE  
> Depends on: NODE-38, NODE-40  
> Produces: Design IR → renderer-neutral compiled scene、增量 patch、资源/字体/样式解析、确定性 render plan / provenance  
> Runtime: `docs/runtime/CANVAS-COMPILER-V1.md`  
> Acceptance: `reports/nodes/NODE-41/acceptance.md`

---

## 1. 目标与实现结论

NODE-41 已建立正式 Canvas Compiler boundary，使 Design IR 与具体 Renderer 保持解耦，同时让 NODE-40 Canvas runtime 和后续 NODE-42 Artifact Engine 共用同一套可复现编译语义。

生产边界：

```text
DesignDocument
→ NODE-38 validation
→ compiler normalization
→ NODE-40 geometry projection
→ style/resource/font resolution
→ text measurement
→ CompiledSceneSnapshot
→ CanvasRenderPlan
→ Renderer Adapter / Artifact Engine
```

编译器不新增第二套持久化文档协议，所有 compiled scene、render plan、runtime URI、字体运行时数据、text metrics 和 Pixi object 均为 disposable state。

## 2. 已实现模块

`@lumi/canvas-sdk` 新增：

```text
compiler-types.ts
compiler-resolvers.ts
compiler-dirty.ts
compiler-cache.ts
compiler.ts
compiler-benchmark.ts
```

测试：

```text
compiler.test.ts
compiler-renderer.test.ts
compiler-benchmark.test.ts
```

校验与证据：

```text
scripts/validate_canvas_compiler.py
docs/runtime/CANVAS-COMPILER-V1.md
reports/nodes/NODE-41/acceptance.md
.github/workflows/canvas-compiler.yml
```

## 3. Compiled Scene Contract

`CompiledSceneNode` 扩展 NODE-40 renderer-neutral scene，只增加渲染需要的派生字段：

```text
resolved_style
style_versions
resolved_text
resolved_resource
interaction_flags
clip_id / mask_id
placeholder
```

并继续保留：

```text
local_matrix
world_matrix
local_bounds
world_bounds
paint_order
visible
locked
```

这些字段不会回写 Design IR。

## 4. Full Compile

`CanvasCompiler.fullCompile()` 已实现：

1. `validateDocument()`；
2. fatal schema/root/cycle gate；
3. deterministic scene/geometry projection；
4. style token resolution；
5. async Asset resolution；
6. async Font resolution；
7. deterministic Text measurement boundary；
8. renderer-neutral render plan；
9. resource/font version collection；
10. canonical SHA-256 `compile_hash`；
11. compile provenance。

Full compile 用于 export / artifact snapshot 等需要完整 hydration 的路径。

## 5. Interactive Structural Compile

NODE-40 `CanvasController` 已改为通过 `CanvasSceneCompilerPort` 构造 scene。

默认实现：

```text
new CanvasCompiler().compileStructure(document)
```

该同步路径只做确定性结构/style/geometry compile，不等待网络 Asset/Font，避免 pointer interaction 被异步资源阻塞。

Canvas 资源驻留继续由 NODE-40 `CanvasAssetResidency` 负责。

## 6. Incremental Compile

`incrementalCompile()` 接收：

```text
previous CompiledSceneSnapshot
before DesignDocument
after DesignDocument
optional SemanticDiff
```

Dirty set 已实现：

```text
changed node
+ inherited/geometry descendants
+ structural/order ancestors
+ removed node former parent
+ asset dependents
+ style token dependents
+ font dependents
```

NODE-38 `semanticDiff()` 不覆盖 resource-table-only 变化，因此 NODE-41 独立比较 `document.resources`，保证 asset/style/font 版本单独变化时也会重编译依赖节点。

## 7. Incremental Full Fallback

以下变化明确 fallback full compile：

```text
schema version change
root change
compiler version change
```

输出 `INCREMENTAL_FALLBACK` diagnostic，不伪装成局部 patch。

## 8. Resource Resolver

已定义可注入接口：

```text
CompilerAssetResolver
CompilerFontResolver
CompilerStyleResolver
CompilerTextMeasurer
```

默认 document resolvers 用于离线/测试确定性路径；生产环境可注入授权 resolver。

资源缺失时：

```text
resolved_resource.status = MISSING
+ RESOURCE_MISSING diagnostic
+ renderer placeholder
```

不把 presigned URL 写回 Design IR。

## 9. Font / Text

Font resolver 以稳定 `font_ref` / resource identity 工作，并输出：

```text
family
version
status
style / weight
runtime uri
fingerprint
```

Text compile 输出：

```text
content
font_ref
resolved font
measured metrics
```

默认 `DeterministicTextMeasurer` 为可重复 fixture/offline implementation；受控 export server 可替换为正式 font-shaping stack 而不改变 compiler contract。

字体 resource version 改变会 dirty 依赖 Text node 并触发 remeasure。

## 10. Style Tokens

`style_refs` 按声明顺序解析，后面的 token 覆盖前面的同名属性。

Compiled node 记录：

```text
resolved_style
style_versions
```

当前直接视觉字段也规范化进入 compiled style：

```text
opacity
blend_mode
```

Style token version 会进入 compile provenance。

## 11. Mask / Clip

Compiler 从 renderer-neutral metadata 解析：

```text
mask_id
clip_id
```

Pixi adapter 在 display objects 创建完后执行第二遍 mask materialization，通过 renderer-neutral `setMask()` 绑定。

Compiler core 不依赖 Pixi。

## 12. Deterministic Compile Hash

同以下输入应产生等价 `compile_hash`：

```text
Design IR visual semantics
compiler version
stable asset/style/font versions
```

Hash 包括：

```text
paint order
matrices / bounds
resolved style + style versions
resolved text + font version + metrics
resolved asset identity/version/dimensions
interaction flags
mask/clip
placeholder state
```

Hash 排除：

```text
presigned asset URI
presigned font URI
GPU/Pixi identity
camera/selection
timestamps
```

已有 regression test 验证仅更换 signed URL token、不改变 stable resource version 时，`compile_hash` 保持一致。

## 13. Compiler Provenance

Full compile 输出：

```text
compiler_version
document_id
schema_version
document_version
resource_versions  # asset + style token
font_versions
compile_hash
```

NODE-42 Artifact Engine 应直接消费该 provenance，而不是从 Pixi/browser state 重建来源信息。

## 14. Cache

已实现 bounded LRU `CanvasCompilerCache`。

Cache key：

```text
canonical Design IR + compiler version
```

Full compile 默认 `useCache=false`。如果生产 resolver 的稳定版本可在 Design IR 外部变化，调用方必须提供 invalidation policy 或禁用 cache，避免 stale resolution。

## 15. Renderer Bridge

NODE-41 已扩展 NODE-40 Pixi bridge：

- Shape/Frame 使用 `resolved_style` fill；
- Text 使用 compiled fill/fontSize/fontFamily/fontWeight/lineHeight/align；
- opacity/blend mode 由 compiled style materialize；
- mask/clip 通过 `setMask()`；
- Pixi runtime object 仍只存在于 adapter/binding 层。

## 16. Error Handling

Fatal：

```text
IR graph cycle
unsupported schema major
invalid root identity
missing document identity
```

Recoverable：

```text
missing style token
missing asset
missing font
resolver error
text measurement error
renderer-unsupported custom node
non-fatal IR diagnostic
```

Recoverable node 错误不会让完整 scene 崩溃；可安全时生成 placeholder + diagnostic。

## 17. Tests

已实现：

- deterministic full compile；
- input immutability；
- signed URI exclusion；
- asset/style/font version provenance；
- missing asset placeholder；
- graph cycle rejection；
- unsupported custom node placeholder；
- full vs incremental compile equivalence；
- resource-only dirty invalidation；
- compiler version full fallback；
- authorized resolver injection；
- cache behavior；
- CanvasController compiler routing；
- compiled style → Pixi bridge；
- mask bridge；
- 2k node / 100 operation benchmark equivalence。

## 18. Benchmark Harness

固定场景：

```text
2,000 logical nodes
100 MOVE_NODE operations
```

执行：

```text
initial full compile
Design Operations
fresh full compile
incremental compile
```

记录：

```text
full compile ms
incremental compile ms
dirty node count
upsert count
fallback flag
full/incremental compile hash equality
```

不在 hosted runner 真正执行前宣称绝对 latency。

## 19. CI

专用 workflow：

```text
.github/workflows/canvas-compiler.yml
```

Jobs：

```text
compiler-contract
compiler-quality
compiler-equivalence
compiler-benchmark
```

分别验证 architecture/typecheck、全量 Canvas regression、full/incremental equivalence 和 2k/100-op benchmark。

## 20. 验收状态

- [x] Design IR 不依赖 Pixi。
- [x] Full compile implemented。
- [x] Incremental compile implemented。
- [x] resource/font/style resolver contracts implemented。
- [x] incremental/full equivalence test implemented。
- [x] compiler version进入 provenance。
- [x] resource/font/style versions进入 provenance。
- [x] Pixi adapter consumes compiled style/mask semantics。
- [x] benchmark harness implemented。
- [x] dedicated CI implemented。
- [ ] Hosted contract/typecheck executes green。
- [ ] Hosted equivalence tests execute green。
- [ ] Hosted benchmark executes green。

## 21. Definition of Done

当前状态：

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

只有以下 hosted jobs **实际执行并通过**后才能标记 COMPLETE：

```text
compiler-contract
compiler-quality
compiler-equivalence
compiler-benchmark
```

如果 GitHub Actions 继续因账户付款 / spending-limit 无法启动 runner，只记录为外部 CI blocker，不标记代码 PASS/COMPLETE。

下一节点：NODE-42 — Artifact Engine。

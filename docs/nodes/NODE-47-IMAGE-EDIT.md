# NODE-47 — Image Edit & Local Edit Pipeline

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / LOVART-PARITY CORE  
> Depends on: NODE-39, NODE-42, NODE-44, NODE-46  
> Produces: 局部编辑、Mask/Region处理、Protected Content保持、新ArtifactVersion

---

## 1. 目标

实现类似“产品和Logo不要动，只把背景换黑色”的精确编辑。系统优先结构化 Canvas/IR 编辑；只有必须改变像素内容时才走生成式 image edit，并经过 hard constraints postflight。

## 2. Edit Planner

输入：

```text
current artifact/design version
user edit intent
selected node/region?
active constraints
brand/identity refs
```

输出 `EditPlan`：

```text
STRUCTURAL_IR_EDIT
PIXEL_LOCAL_EDIT
REGENERATE_REGION
FULL_IMAGE_EDIT
HYBRID
```

原则：最小修改面。

## 3. Structural First

可以通过 Design IR完成的：

```text
move/resize text
change font/color
background vector color
replace existing image node
reorder layers
```

不得调用生成模型。

## 4. Pixel Edit Spec

```text
source_asset/version
editable_mask
protected_masks[]
reference_assets[]
instruction
identity_requirements
expected unchanged regions
output dimensions
```

Mask坐标与原图像素空间显式转换，保存version/hash。

## 5. Mask Generation

来源：

- user brush/selection；
- Design IR node bounds/mask；
- segmentation/detector；
- Agent proposed + preview。

高影响自动mask应可在 UI预览。

## 6. Protected Content

Product/Logo/QR等：

```text
PROTECT_REGION
LOCK_IDENTITY
LOCK_CONTENT/TRANSFORM
```

Provider prompt不是保障；结果回来后实际 validator检查。

## 7. Provider Capability

Router按：

```text
image.edit
mask edit
reference preservation
input/output size
```

选择。若 provider不支持精确mask，不应用于 hard local edit，除非用户明确允许更大变化。

## 8. Postflight

必须：

- protected-region visual diff；
- Identity Engine；
- QR decode；
- OCR for locked text/logo wordmark；
- resolution；
- intended region是否真正变化。

输出 PASS / REPAIR / REJECT。

## 9. Versioning

永远：

```text
v3 source
→ edit
→ v4 candidate
```

不覆盖 v3。失败 candidate可保留内部debug ref，但普通历史只展示有意义版本，按policy cleanup。

## 10. Edit Provenance

记录 source version、mask hash、protected regions、provider/model、instruction hash、constraint snapshot、validation scores。

## 11. Fallback

若精确生成式编辑连续失败：

- 尝试另一符合capability provider；
- 分层合成策略，例如只生成背景再 compositing protected product；
- 要求用户确认更大范围编辑。

不得为“完成任务”偷偷违反 hard locks。

## 12. Canvas Integration

编辑完成：ArtifactVersion → asset resolver → update Design IR image node via `REPLACE_ASSET` → new DesignDocumentVersion；这两个版本关系写 lineage。

## 13. Benchmarks

核心 acceptance：

```text
A: unchanged product
B: unchanged logo
C: unchanged QR + decodable
D: requested background changed
E: title resize structural no generation
```

建立 100+ local edit cases。

## 14. Tests

- structural route；
- mask coordinate；
- protected region；
- wrong provider capability；
- QR locked；
- fallback compositing；
- version lineage；
- retry idempotency。

## 15. 验收标准

- [ ] structural edit优先。
- [ ] mask/protected区域可追溯。
- [ ] hard lock postflight。
- [ ] failure不会覆盖原版本。
- [ ] Canvas/Artifact lineage完整。
- [ ] “只改背景”黄金场景通过。

## 16. Definition of Done

```text
local edit pipeline implemented
+ golden constraint suite green
+ provider edit benchmark green
```

下一节点：NODE-48 Video Generation。

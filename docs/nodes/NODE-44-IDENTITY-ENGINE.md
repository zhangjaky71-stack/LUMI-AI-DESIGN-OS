# NODE-44 — Identity Engine

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 QUALITY  
> Depends on: NODE-18, NODE-39, NODE-45 interfaces  
> Produces: Product/Logo/Character Identity Reference Set、相似度验证、阈值校准与 violation

---

## 1. 目标

解决“还是不是同一个东西”。Visual Critic判断好不好看；Identity Engine判断商品、Logo、人物/角色在生成和编辑后是否保持身份。

## 2. Identity Types

```text
PRODUCT
LOGO
CHARACTER
FACE (受隐私/用途政策约束)
STYLE_REFERENCE (soft)
```

P0重点 PRODUCT + LOGO；Character P1；Face必须经过更严格隐私/安全审查，不自动开启生物识别型长期索引。

## 3. Reference Set

```text
identity_id
organization_id
project/brand scope
type
canonical_asset_ids[]
reference_views[]
notes
threshold_profile
version
```

多角度产品图可提高鲁棒性。

## 4. Signals

按类型组合：

### Logo

- vector/hash exact when available；
- perceptual image compare；
- feature matching；
- OCR/wordmark optional。

### Product

- multimodal embedding；
- local feature/shape/color cues；
- detected brand/logo region；
- VLM structured compare作为补充。

不依赖单一 embedding分数。

## 5. Crop / Detection

先定位 target region。Design IR中产品 node已有 bounds时直接用；整图生成时通过 detector/VLM region proposal，并保存 evidence。

## 6. Score

```text
identity_score 0-100
confidence
signal_scores
threshold_profile
```

阈值按场景校准：背景替换比“创意重绘”要求更高。

## 7. Calibration Dataset

建立正/负/near-miss：

- 同产品不同光照/角度；
- 颜色错误；
- Logo变形；
- 包装文字改变；
- 类似但不同SKU。

用 ROC/precision-recall 等统计选择阈值，不能拍脑袋 0.8。

## 8. Hard vs Soft

User明确“产品不能变” → hard threshold。

创意探索“参考这个产品风格” → soft/advisory。

## 9. Privacy

Face/人物身份：

- 只在明确功能需要时处理；
- 权限/retention；
- 不跨租户建立全局脸库；
- 不把身份embedding用于无关推断。

## 10. API/Internal

```text
create_reference_set
validate(candidate, identity_id, profile)
compare(a,b,type)
```

输出 evidence refs给 Constraint/Critic。

## 11. Failure Policy

validator unavailable + hard identity：fail closed或进入人工 review，不能当通过。

## 12. Tests

- exact logo；
- stretched/recolored logo；
- same product background changes；
- wrong SKU；
- low-quality crop；
- missing target；
- threshold profile/version。

## 13. 验收标准

- [ ] Product/Logo reference sets。
- [ ] 多信号而非单一embedding。
- [ ] calibrated dataset。
- [ ] hard identity接 Constraint Engine。
- [ ] evidence/version可追溯。
- [ ] 不建立跨租户人脸索引。

## 14. Definition of Done

```text
identity validation service implemented
+ calibration report
+ product/logo benchmark green
```

下一节点：NODE-45 Asset Intelligence。

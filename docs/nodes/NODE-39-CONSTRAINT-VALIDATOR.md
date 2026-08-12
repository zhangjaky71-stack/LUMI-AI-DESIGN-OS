# NODE-39 — Constraint Validator Runtime

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-14, NODE-38, NODE-44 interfaces  
> Produces: Preflight/Postflight validator、违规聚合、QR/几何/品牌/身份插件接口

---

## 1. 目标

实现真正执行 NODE-14 规则的验证器。它必须既能阻止结构化 Design Operation 破坏锁定元素，又能在生成式编辑后检查像素结果是否破坏产品、Logo、二维码等。

## 2. Runtime Pipeline

```text
Design Operation
→ resolve effective constraints
→ preflight evaluators
→ ALLOW/DENY
→ execute/render/generate
→ postflight evaluators
→ violation aggregation
→ PASS/REPAIR/FAIL
```

## 3. Evaluator Interface

```python
class ConstraintEvaluator:
    type: str
    def preflight(context, operation) -> EvalResult
    def postflight(context, before_ref, after_ref) -> EvalResult
```

不是每种 constraint 都需要两阶段；必须明确 support flags。

## 4. Geometry Evaluators

实现：

```text
LOCK_POSITION
LOCK_SIZE
LOCK_ROTATION
LOCK_TRANSFORM
LOCK_ASPECT_RATIO
LOCK_LAYER_ORDER
LOCK_PARENT
MUST_STAY_INSIDE
MUST_NOT_OVERLAP
MIN_MARGIN
SAFE_AREA
```

误差使用 tolerance profile，避免浮点微差误报。

## 5. Content Evaluators

```text
LOCK_TEXT
LOCK_CONTENT
LOCK_ASSET
LOCK_STYLE
LOCK_BRAND
```

结构化 IR 直接比较 normalized fields；不需要调用 LLM。

## 6. Protected Region

Postflight 输入：before/after image + region mask。

比较多种信号：

```text
SSIM/perceptual diff
edge/feature difference
color difference
optional embedding similarity
```

容忍压缩/抗锯齿，threshold 通过校准 dataset 决定。

## 7. QR Validator

必须用真实 QR decoder 验证：

```text
detected
payload same
readable at export target size
quiet zone warning
```

Hard QR requirement fail 时禁止 APPROVED/export。

## 8. Contrast / Readability

结构化文本场景优先计算 foreground/background contrast；复杂图片背景可通过采样/vision grader补充。规则记录 accessibility/design profile，不声称所有艺术场景都必须 WCAG 文本阈值，除非产品设置要求。

## 9. Brand / Identity 插件

通过 interface 调 NODE-43/44：

```text
BrandComplianceValidator
IdentitySimilarityValidator
```

Constraint Runtime 不 hardcode embedding model。

## 10. Violation Aggregator

同一根因不要生成 20 条重复 warning。聚合：

```text
constraint_id
severity
node/region
validator
score
threshold
reason_code
repair_hint
raw_evidence_ref
```

## 11. Override

Runtime 验证 override token：

```text
constraint_id
artifact/design version
actor
reason
expires/one-time
```

过期/stale version override 不能套用新版本。

## 12. Deterministic First

规则：能以 IR/geometry/hash 精确判断的约束，禁止默认用 LLM/VLM 代替。

## 13. Benchmark Dataset

至少：

- 100 structure locks；
- 50 QR variants；
- 50 protected-region edits；
- 50 product/logo identity cases；
- known compression false-positive cases。

## 14. Tests

- tolerance edge；
- stale constraint snapshot；
- override；
- batch violation；
- QR payload changed；
- protected mask small antialias change；
- validator timeout/failure policy。

Validator 本身故障不能把 hard constraint 当 PASS；返回 `VALIDATION_UNAVAILABLE` 并按 policy阻断高风险批准。

## 15. 验收标准

- [ ] V1 hard locks 有 runtime evaluator。
- [ ] QR 实际 decode 校验。
- [ ] postflight 插件机制。
- [ ] validator fail-closed policy 对关键规则生效。
- [ ] violation report 结构化。
- [ ] benchmark/false-positive 数据存在。

## 16. Definition of Done

```text
constraint runtime implemented
+ core evaluator suite green
+ postflight benchmark calibrated
```

下一节点：NODE-40 Canvas Engine。

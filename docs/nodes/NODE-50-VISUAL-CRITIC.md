# NODE-50 — Visual Critic & Design Quality Engine

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / QUALITY CORE  
> Depends on: NODE-39, NODE-43, NODE-44, NODE-22, NODE-05  
> Produces: 多信号Visual QA、设计评分、结构化Critique、Quality Gate

---

## 1. 目标

在生成后自动判断“是否达标、哪里有问题、是否可修复”。不能只让生成它的同一个Agent说“很好”。Quality Engine组合 deterministic rules、CV/OCR、Identity、Brand和独立VLM/critic。

## 2. Quality Dimensions

```text
constraint compliance
composition
visual hierarchy
alignment/spacing
typography/readability
contrast
brand consistency
identity consistency
text accuracy
logo integrity
QR readability
image defects
resolution/export readiness
```

## 3. Evidence Sources

优先：

```text
Constraint Runtime
Design IR geometry
OCR
QR decoder
Identity Engine
Brand Validator
Image metadata
independent visual model grader
human feedback dataset
```

## 4. Score Model

每维：

```text
score 0-100
confidence
evidence
threshold
severity
```

总分不是简单平均：Hard gate先行。

```text
hard constraint fail => FAIL
else weighted quality profile => score
```

## 5. Quality Profiles

```text
exploration
production-web
brand-strict
product-strict
print
social-fast
```

不同profile权重/阈值不同；exact version保存。

## 6. Critic Model Isolation

生产图像Agent与Critic尽量使用不同prompt/role，必要时不同模型。Critic只能提出assessment/repair plan，不直接批准自己刚生成内容。

## 7. Structured Critique

```json
{
  "status": "FAIL_REPAIRABLE",
  "overall_score": 74,
  "violations": [],
  "strengths": [],
  "repair_actions": [
    {"type":"SET_PROPERTY","target":"headline","reason":"..."}
  ],
  "confidence": 0.86
}
```

Repair action必须映射DesignOps/registered edit command，不能只写散文。

## 8. Typography

结构化Design IR优先：bounding boxes、font size、line height、overflow、contrast。Raster生成图补OCR与VLM。检测乱码/错字/被截断。

## 9. Composition

VLM评分需用anchor examples/human pairwise校准。不要把主观“高级感”直接硬编码成绝对事实。

## 10. Defect Detection

图片：异常手指/物体、重复、文字破碎、明显生成artifact等由VLM/CV评估；对产品图 identity比审美优先。

## 11. Calibration

每个grader：

- human-labeled set；
- false positive/negative；
- inter-rater agreement；
- threshold revision版本。

LLM/VLM grader模型更新必须重新benchmark。

## 12. Quality Gate

```text
PASS
PASS_WITH_WARNINGS
FAIL_REPAIRABLE
FAIL_HARD
REVIEW_REQUIRED
```

低confidence +高影响进入人工review。

## 13. LangSmith

Critic trace/experiment可进LangSmith；最终QualityResult写LUMI DB/Artifact metadata，不依赖LangSmith在线可用才保存质量。

## 14. Tests

- hard QR fail；
- brand font fail；
- product identity fail；
- known typography overflow；
- visual grader timeout；
- low-confidence review；
- model-version calibration。

## 15. 验收标准

- [ ] deterministic signals优先。
- [ ] Hard gate不能被总分掩盖。
- [ ] Critique结构化可修复。
- [ ] grader有版本/校准数据。
- [ ] visual model故障有fallback/review，不误PASS。
- [ ] Artifact记录QualityResult。

## 16. Definition of Done

```text
quality engine implemented
+ calibrated benchmark report
+ quality gate integration green
```

下一节点：NODE-51 Auto Repair。

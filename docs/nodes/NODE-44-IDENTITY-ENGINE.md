# NODE-44 — Identity Engine

> Phase: 5 Design Intelligence  
> Status: IMPLEMENTED / VALIDATING / not COMPLETE  
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
threshold_profile_id
threshold_profile_version
version
```

Reference Set绑定 canonical asset **及其版本**。多角度产品图可提高鲁棒性；升级参考图创建新版本，不改写历史验证。

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

不依赖单一 embedding分数。NODE-44 P0 Product/Logo profile要求至少两个独立 required signals。

## 5. Crop / Detection

先定位 target region。Design IR中产品 node已有 bounds时直接用；整图生成时通过 detector/VLM region proposal，并保存 evidence。没有 bounds/detector evidence/显式 whole-artifact target 时，返回 `IDENTITY_TARGET_REGION_UNAVAILABLE`，不得静默使用整图。

## 6. Score

```text
identity_score 0-100
confidence
signal_scores
threshold_profile_id/version
calibration_dataset_version
provider/preprocessor version
```

阈值按场景校准。高相似但低 confidence 的低质量 crop 进入 `REVIEW`，不能自动 PASS。

## 7. Calibration Dataset

建立正/负/near-miss：

- 同产品不同光照/角度；
- 颜色错误；
- Logo变形；
- 包装文字改变；
- 类似但不同SKU。

用 precision/recall/F1/FPR/FNR、ROC AUC、average precision 选择和记录 operating point，不能拍脑袋设置 0.8。Constraint参数不得用 numeric threshold覆盖已发布 calibration profile。

仓库 `fixtures/identity/node-44-calibration.json` 仅为 synthetic conformance fixture；真实生产阈值仍需按 `reports/nodes/NODE-44/calibration.md` 建立 approved benchmark 后发布。

## 8. Hard vs Soft

User明确“产品不能变” → HARD calibrated profile。

创意探索“参考这个产品风格” → SOFT/ADVISORY。`STYLE_REFERENCE` 不允许升级成 HARD identity lock。

## 9. Privacy

Face/人物身份：

- 默认 `allow_face_processing=false`；
- 只在明确功能需要并有显式 consent/purpose/retention 时处理；
- runtime + DB 禁止 persistent biometric index；
- 不跨租户建立全局脸库；
- 不把身份embedding用于无关推断；
- Artifact provenance只保存 aggregate validation snapshot id，不保存 raw face embedding/template。

## 10. Runtime API/Internal

```text
build/select calibration profile
validate(candidate, identity reference set, calibrated profile)
identityValidationBatchSnapshotId(reports)
IdentitySimilarityValidator adapter
Artifact approval gate
```

输出 evidence refs给 NODE-39 Constraint/Critic，并生成 deterministic `identity-validation:<sha256>` 与 `identity-batch:<sha256>`。

## 11. Failure Policy

validator unavailable + hard identity：交给 NODE-39 既有 fail-closed postflight policy；NODE-44 adapter抛出不可用/版本错配，不另造第二个 blocker。

以下情况均不得静默 PASS：

```text
reference/profile version mismatch
provider/preprocessor mismatch
required signal unavailable
missing target evidence
cross-tenant reference/candidate
low confidence
HARD validator unavailable
```

## 12. Tests

已实现：

- exact logo；
- stretched/recolored logo；
- same product background changes；
- wrong SKU；
- low-quality crop -> REVIEW；
- missing target；
- required signal unavailable；
- threshold/profile/provider/preprocessor version；
- cross-tenant；
- Face default deny；
- cache version invalidation；
- NODE-39 adapter；
- Artifact snapshot/hash/approval compatibility。

## 13. Persistence

`db/migrations/0003_identity_engine.sql`：

```text
identity_threshold_profiles
identity_calibration_samples
identity_reference_sets
identity_reference_views
identity_validation_reports
identity_validation_batches
artifact_versions.identity_validation_snapshot_id
artifact_provenance.identity_validation_snapshot_id
```

数据库使用 `logical id + version` composite tenant keys，而不是把 logical id 本身做不可版本化的唯一 PK。

## 14. NODE 集成边界

- **NODE-18 Asset Storage**：负责 upload/scan/checksum/MIME/rights；NODE-44只消费 READY verified asset。
- **NODE-39 Constraint Validator**：拥有 HARD postflight blocker；NODE-44实现 `IdentitySimilarityValidator`。
- **NODE-42 Artifact Engine**：记录 exact aggregate identity snapshot并执行 approval gate。
- **NODE-43 Brand Rules**：Logo/brand identity可作为品牌合规的语义验证补充，但不重写 deterministic Brand rules。
- **NODE-45 Asset Intelligence**：负责全局 OCR/embedding/object/search/index；NODE-44只消费其版本化分析信号，不抢占搜索职责。

## 15. Runtime / Evidence Files

```text
packages/identity-engine/src/*
services/identity-engine/src/lumi_identity_engine/*
services/identity-engine/tests/test_identity_engine.py
fixtures/identity/node-44-calibration.json
db/migrations/0003_identity_engine.sql
scripts/validate_identity_engine.py
scripts/benchmark_identity_engine.py
docs/runtime/IDENTITY-ENGINE-V1.md
reports/nodes/NODE-44/calibration.md
reports/nodes/NODE-44/acceptance.md
.github/workflows/identity-engine.yml
```

## 16. 验收标准

- [x] Product/Logo reference sets。
- [x] 多信号而非单一embedding。
- [x] calibration machinery + labeled conformance fixture。
- [ ] real-world production calibration dataset / operating point review。
- [x] hard identity接 Constraint Engine。
- [x] evidence/version可追溯。
- [x] 不建立跨租户/持久化人脸索引。
- [ ] hosted contract/quality/integration/benchmark实际执行 green。

## 17. Definition of Done

当前工程状态：

```text
identity validation service implemented
+ calibration/conformance report implemented
+ product/logo benchmark gate implemented
+ hosted CI pending execution
```

**不能在 hosted `identity-contract / identity-quality / identity-integration / identity-benchmark` 真正执行 green 前标记 COMPLETE。**

下一节点：NODE-45 Asset Intelligence。

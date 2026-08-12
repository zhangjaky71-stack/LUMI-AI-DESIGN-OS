# NODE-46 — Image Generation Pipeline

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE PRODUCT  
> Depends on: NODE-22, NODE-23, NODE-27, NODE-42, NODE-45  
> Produces: 多模型图片生成服务、Reference/Variant策略、Artifact/Cost/Provenance闭环

---

## 1. 目标

把图片生成从“调用某个 API”升级为生产级 pipeline：输入 Design Intent/Brief/References/Constraints，自动选择模型、控制尺寸与数量、记录成本/血缘，产出可进入 Canvas 和版本系统的 Artifact candidate。

## 2. Request Spec

```text
ImageGenerationSpec
├─ project_id/task_id/operation_id
├─ purpose
├─ prompt_compilation_ref
├─ aspect_ratio
├─ target_width/height
├─ variant_count
├─ references[]
├─ identity_requirements[]
├─ brand_rule_set_version
├─ constraints[]
├─ quality_profile
├─ budget_limit
└─ output_requirements
```

Agent只能生成 spec；Provider-native payload由 Model Gateway负责。

## 3. Generation Modes

```text
TEXT_TO_IMAGE
REFERENCE_TO_IMAGE
PRODUCT_SCENE
STYLE_REFERENCE
TRANSPARENT_ASSET
BACKGROUND_GENERATION
COMPOSITION_EXPLORATION
```

模式映射 required capabilities，Router据此选模型。

## 4. Reference Selection

通过 Asset Intelligence选择：

- approved product images；
- logo assets；
- brand references；
- moodboard；
- user explicitly attached refs。

每个 reference保存作用：`IDENTITY / STYLE / COMPOSITION / CONTENT`，防模型混淆。

## 5. Prompt Compilation

Prompt Compiler生成 provider-neutral blocks：

```text
objective
content
visual direction
brand constraints
identity requirements
negative constraints
output dimensions
```

实际 provider adapter再转换。不把用户原始prompt直接无条件拼给所有模型。

## 6. Variant Strategy

Variant count由 Recipe + Budget决定。

例如：

```text
exploration profile → 4 candidates
precision edit profile → 1-2 candidates
```

预算不足时减少 variants必须生成 decision reason，不偷偷降低 hard resolution/identity requirement。

## 7. Job Lifecycle

同步 provider：SideEffectGateway → invoke → result。

异步 provider：

```text
submit
→ provider_request_id
→ PENDING
→ poll/webhook worker
→ READY/FAILED
```

HTTP/Graph不占用长连接等待。

## 8. Output Validation

下载/接收结果后：

- checksum；
- MIME；
- dimensions；
- decode；
- empty/corrupted image；
- content safety metadata；
- optional OCR；
- hard constraint postflight；
- identity checks。

不合格不得直接变 APPROVED。

## 9. Artifact Creation

每 candidate：

```text
Object Storage file
→ Asset/ArtifactFile
→ ArtifactVersion DRAFT/READY
→ provenance
→ visual critic later
```

原 provider URL不作为长期真相。

## 10. Provenance

记录：

```text
provider/model/revision if known
provider request id
prompt/template hash
reference assets
seed if supplied
size/quality params
routing reason
cost/pricing snapshot
agent/skill/recipe
code git sha
```

## 11. Safety / Rights

输入 references先检查 access/rights；生成结果记录 provider safety metadata和用户用途声明。不能因为模型生成就自动宣称“无版权风险”。

## 12. Cost

调用前 reserve，后 actual；失败也可能产生 provider cost，按真实计费记录。相同 operation retry走 NODE-20。

## 13. Cache / Reuse

仅对语义完全等价且产品允许的 deterministic-ish operation做内容缓存；创作型请求默认不因为 prompt hash相同就强制返回旧图。可提供“reuse identical export”，不要误缓存用户期望的新随机探索。

## 14. Events

```text
generation.started
generation.provider_submitted
generation.completed
generation.failed
artifact.version.created
```

## 15. Benchmarks

至少：

- Chinese poster text fidelity；
- product consistency；
- brand style；
- multiple aspect ratios；
- transparent asset；
- cost/latency；
- fallback。

## 16. Tests

- MockProvider deterministic；
- 429 fallback；
- async completion；
- corrupted output；
- budget insufficient；
- duplicate retry；
- rights-filtered reference；
- provenance completeness。

## 17. 验收标准

- [ ] 多 provider可插拔。
- [ ] Reference role结构化。
- [ ] variant/budget联动。
- [ ] output经过验证。
- [ ] Artifact/Cost/Provenance完整。
- [ ] paid retry不重复。
- [ ] live provider有benchmark结果后才进入production routing。

## 18. Definition of Done

```text
image generation pipeline implemented
+ mock E2E green
+ selected live adapters benchmarked
+ artifact/cost/provenance reconciliation green
```

下一节点：NODE-47 Image Edit。

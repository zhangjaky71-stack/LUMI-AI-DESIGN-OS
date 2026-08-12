# NODE-07 — Model Provider Matrix

> Phase: 0 Benchmark Before Build  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-05, NODE-06  
> Produces: 供应商/模型能力数据库、质量成本延迟基线、首批 Provider Adapter 清单

---

## 1. 目标

LUMI 不绑定单一模型。此节点建立一个可持续更新的 Model Provider Matrix，用事实回答：某个任务应当调用谁、为何调用、失败后切换谁、预计成本多少。

模型名称、价格和能力变化快，因此文档只冻结评估方法和首批 provider family；实施时必须从官方 provider 文档/API 再核验并生成 `observed_at` snapshot。

## 2. Provider Families

首批调研至少包含：

### Language / Multimodal reasoning

- OpenAI
- Google
- Anthropic
- 可用且合规的开放模型托管商

### Image generation/edit

- OpenAI image family
- Google image family
- Black Forest Labs / FLUX family
- 其他具备生产 API、商业条款清晰且质量通过 benchmark 的 provider

### Video

- Google / Veo family
- Runway
- 其他通过 release benchmark 的 API provider

### Embedding / Rerank / OCR

优先可替换 adapter；避免为了单一辅助任务引入不可迁移业务逻辑。

## 3. Model Record

```yaml
provider: google
model_id: "provider-native-id"
observed_at: "2026-08-12"
capabilities:
  text: true
  vision_input: true
  image_generate: false
  image_edit: false
  video_generate: false
  structured_output: true
limits:
  context_window: null
  max_images: null
pricing:
  unit: "..."
  input: null
  output: null
quality:
  planning_score: null
  chinese_text_score: null
  image_edit_score: null
operations:
  median_latency_ms: null
  p95_latency_ms: null
  availability: null
legal:
  commercial_use_reviewed: false
```

## 4. Capability Taxonomy

```text
REASONING
STRUCTURED_OUTPUT
TOOL_CALLING
VISION_UNDERSTANDING
LONG_CONTEXT
IMAGE_GENERATION
IMAGE_EDIT
MASK_EDIT
REFERENCE_IMAGE
PRODUCT_CONSISTENCY
TEXT_IN_IMAGE
TRANSPARENT_BG
UPSCALE
VIDEO_TEXT_TO_VIDEO
VIDEO_IMAGE_TO_VIDEO
AUDIO
EMBEDDING
RERANK
OCR
```

能力不能只用 boolean；后续 Capability Registry 支持等级、限制和 confidence。

## 5. 任务基准

至少 benchmark：

### LLM

- Brief extraction；
- long project planning；
- Design IR structured output；
- tool selection；
- Chinese copywriting；
- critic reasoning。

### Image

- 中文商业海报文字；
- product identity；
- background replacement；
- local edit；
- reference style adherence；
- transparent background；
- 1:1 / 4:5 / 9:16。

### Video

- product motion；
- character consistency；
- camera instruction；
- source-image adherence；
- duration and resolution。

## 6. 评分

每种 task profile：

```text
quality_score      0-100
constraint_score   0-100
latency_score      0-100
cost_score         0-100
availability_score 0-100
```

Router 不直接使用一个总分；不同 TaskPolicy 设置权重。

例如：

```text
image_edit.precision:
quality 45%
constraint 35%
latency 10%
cost 10%
```

## 7. Provider Adapter Contract 预定义

所有 provider 必须被标准化成：

```text
request capability
normalize inputs
estimate cost
invoke
normalize output
capture provider request id
capture usage
classify error
```

禁止 Agent 知道 provider-native request body。

## 8. Error Taxonomy

统一：

```text
AUTH_ERROR
RATE_LIMIT
TIMEOUT
PROVIDER_5XX
CONTENT_BLOCKED
INVALID_REQUEST
CAPABILITY_UNAVAILABLE
INSUFFICIENT_QUOTA
UNKNOWN
```

后续 Model Gateway 基于分类做 retry/fallback。

## 9. Price Snapshot

任何价格数据必须：

- 保存 currency；
- 保存单位；
- 保存 source；
- 保存 observed_at；
- 不把营销免费额度当真实长期成本；
- price change 后重新计算 routing policy。

## 10. 无 Key 情况

如果真实商业 Key 尚未提供：

1. 创建 MockProvider；
2. provider matrix 仍可通过官方文档填能力；
3. live benchmark 标 `NOT_MEASURED`，不得伪造分数；
4. 工程继续开发，不阻塞。

## 11. 输出

```text
docs/models/MODEL-PROVIDER-MATRIX.md
evals/datasets/model-routing/
config/model-registry.seed.yaml
```

## 12. 验收标准

- [ ] 至少覆盖 reasoning/image/video 三大类。
- [ ] 所有数据有时间戳和来源。
- [ ] 能力与价格分开维护。
- [ ] 建立任务级评分，不用“最好模型”单一标签。
- [ ] 明确 fallback 候选。
- [ ] 没有 Key 时真实值标 NOT_MEASURED。
- [ ] Provider Adapter contract 可支持 NODE-22。

## 13. Definition of Done

```text
provider snapshot committed
+ benchmark profiles defined
+ model candidates ranked per task
+ adapter candidates selected
+ unknowns explicitly marked
```

下一节点：NODE-08 Canvas Technology Spike。

# NODE-07 — Model Provider Matrix

> Phase: 0 Benchmark Before Build  
> Status: **VALIDATING**  
> Implementation Status: **VALIDATING**  
> Implementation Branch: `node-07-model-provider-matrix`  
> Acceptance Report: `reports/nodes/NODE-07/acceptance.md`  
> Registry Version: `1.0.0`  
> Observed At: `2026-08-13`  
> Pricing Snapshot Expires: `2026-09-12`  
> Priority: P0  
> Depends on: NODE-05, NODE-06  
> Produces: 供应商/模型能力数据库、价格/生命周期快照、任务级候选路由、Live Benchmark 合同

---

## 1. 目标

LUMI 不绑定单一模型。NODE-07 建立可持续更新的 Model Provider Matrix，用官方事实回答“哪些模型具备哪些公开能力、处于什么生命周期、官方如何计价、应进入哪些任务候选集”。

NODE-07 **不提前宣布某个模型最好**。质量、毫秒延迟、真实失败率和实际任务成本必须通过 NODE-05 Benchmark Harness 的 live provider benchmark 才能形成 LUMI 实测数据。

## 2. v1 Provider Scope

当前首批五家 Provider：

```text
OpenAI
Google Gemini API
Anthropic Claude API
Black Forest Labs
Runway API
```

覆盖：

```text
reasoning / multimodal vision
image generation
image edit
video generation
video edit
text embedding
multimodal embedding
OCR-like multimodal extraction route
structured rerank route
```

OCR / rerank 暂时保持可替换能力路由，不为了辅助任务提前锁定额外专用厂商。

## 3. Machine-readable Registry

```text
docs/models/
├─ provider-matrix-manifest.json
├─ provider-sources.json
├─ route-candidates.json
└─ providers/
   ├─ openai.json
   ├─ google.json
   ├─ anthropic.json
   ├─ black-forest-labs.json
   └─ runway.json

config/
└─ model-registry.seed.json
```

v1.0.0 Snapshot：

```text
5 providers
28 model records
27 route-eligible models
23 stable
4 preview
1 deprecated
30 first-party source records
15 task routes
0 live-measured model winners
```

## 4. Lifecycle Contract

```text
stable      → 可进入 benchmark；通过后可作为 primary/fallback
preview     → 可进入 benchmark；生产路由必须有风险/回退策略
deprecated  → 不可 route eligible
legacy      → 不可 route eligible
shutdown    → 不可 route eligible
```

注册表保留一个 deprecated sentinel，确保陈旧模型不能误入候选路由。

## 5. Measurement Truthfulness

若没有执行 LUMI live benchmark：

```json
{
  "benchmark_status": "NOT_MEASURED",
  "quality": "NOT_MEASURED",
  "latency_ms": "NOT_MEASURED"
}
```

禁止：

- 把厂商“fastest/frontier/studio quality”等营销/定位转成 LUMI 数值分数；
- 根据聊天主观印象宣布 winner；
- 在无商业 Key/预算时伪造 P50/P95 latency；
- 把 preview model 当无回退的永久生产 primary。

## 6. Price Snapshot Contract

每条价格保存 provider-native unit、USD 数值、官方 source、`observed_at` 和 `pricing_expires_at`。

必须保留特殊价格语义，不能强行压平为单一数字：

```text
input / cached input / output token
context-length tier
promotion expiry
image token output
per-megapixel image price
per-image floor
per-video-second
minimum generation charge
multimodal embedding modality price
```

v1 价格快照最多使用 30 天；到期后需要重新核验官方文档。

## 7. Task Routes

`docs/models/route-candidates.json` 当前定义 15 条候选路由：

```text
reasoning.director
reasoning.default
reasoning.fast
vision.ocr
retrieval.rerank
image.general
image.hero
image.text_heavy
image.local_edit
image.fast_variants
video.general
video.fast
video.edit
embedding.text
embedding.multimodal
```

所有 `selected_primary = null`。

路由候选集不是 ranking 结果，只是 live benchmark 输入。

## 8. Benchmark Profiles

`evals/datasets/model-provider/suite.json` 定义：

```text
reasoning:
  brief decomposition
  long project planning
  constraints
  tool selection
  repair decision

vision / retrieval:
  poster text extraction
  layout geometry
  multilingual read
  asset/doc rerank

image:
  general prompt adherence
  premium hero
  typography / multilingual poster text
  local edit
  product/logo/QR protection
  fast variants / cost throughput

video:
  storyboard adherence
  identity consistency
  motion
  audio
  duration/aspect
  edit preservation

embedding:
  brand document retrieval
  asset search
  cross-modal retrieval
```

核心实测 dimensions：

```text
task_success
constraint_success
quality
latency_ms
cost_usd
failure_rate
```

## 9. Live Benchmark Safety

NODE-07 live suite：

```text
execution_status = SPECIFIED_NOT_RUN
live_policy = SKIPPED_WITHOUT_PROVIDER_KEY_AND_POSITIVE_BUDGET
```

没有 provider key 和明确正数预算时，必须 `SKIPPED`，不能 PASS。

## 10. Provider Adapter Contract for NODE-22

统一调用流程：

```text
resolve capability route
→ validate lifecycle / provider health
→ normalize request
→ estimate worst-case cost
→ budget/quota check
→ invoke provider
→ normalize result
→ capture provider request/task id
→ capture usage/actual cost
→ persist artifact/provenance
→ classify error/refusal
```

Agent / business graph 禁止直接构造 provider-native payload。

统一错误至少：

```text
AUTH_ERROR
RATE_LIMIT
TIMEOUT
PROVIDER_5XX
CONTENT_BLOCKED
REFUSAL
INVALID_REQUEST
CAPABILITY_UNAVAILABLE
INSUFFICIENT_QUOTA
UNKNOWN
```

## 11. Runtime Seed Contract

`config/model-registry.seed.json` 明确：

```text
source of truth = docs/models/providers/*.json
route by capability route name
no application hard-coded provider/model IDs
benchmark required before primary selection
staleness = 30 days
```

NODE-22/23 实施时将这些记录正规化进入 Model Gateway / Capability Registry，而不是把当前 JSON 当最终生产数据库。

## 12. CI Contract

新增：

```bash
make model-provider-validate
```

Validator：`scripts/validate_model_provider_matrix.py`

它强制检查：

- 五家 Provider 覆盖；
- 官方 first-party source host；
- 日期与 price expiry；
- 28 model / 27 eligible；
- lifecycle 计数；
- reasoning/image/edit/video/embedding 能力覆盖；
- active candidate 必须有官方价格；
- inactive lifecycle 不可 route eligible；
- 未实测质量/延迟必须保持 `NOT_MEASURED`；
- route candidate 必须存在且 eligible；
- preview-only route 必须有 stable fallback；
- `selected_primary` 在 live benchmark 前必须为 null；
- 所有 15 route 都必须映射 benchmark group；
- live benchmark 必须保持明确 SKIPPED policy。

Validator 已接入 `scripts/ci-contracts`，并由 `evals/tests/test_model_provider_matrix_contract.py` 做 Python 回归测试。

## 13. Human-readable Matrix

完整可读报告：

- `docs/models/MODEL-PROVIDER-MATRIX.md`

它记录当前模型族、任务候选集、生命周期、价格快照、Adapter 约束和刷新策略，但不会把尚未测量的数据伪装成排名。

## 14. 验收标准

- [x] 覆盖 reasoning/image/video/embedding，并包含 image/video edit。
- [x] 至少五家 Provider。
- [x] 所有能力/价格/lifecycle 记录有时间戳和 first-party source。
- [x] 能力和价格可独立演进。
- [x] 建立 15 个任务级候选路由，而不是单一“最好模型”。
- [x] preview lifecycle 有稳定回退规则。
- [x] 无 live benchmark 时真实值为 `NOT_MEASURED`。
- [x] Provider Adapter contract 可支持 NODE-22。
- [x] Live suite 无 Key/预算时必须 SKIPPED。
- [x] Registry validator 接入 CI contracts。
- [ ] Implementation PR 完整 NODE-04/05/06 gates 全绿并归档。

## 15. Definition of Done

```text
provider source snapshot                 PASS
model registry v1                       PASS
price/lifecycle snapshot                PASS
15 task candidate routes                PASS
live benchmark profiles                 PASS
provider adapter contract               PASS
unknowns explicitly NOT_MEASURED        PASS
registry validator                      PASS
CI contract integration                 PASS
clean implementation PR validation      PENDING
```

下一节点：NODE-08 Canvas Technology Spike。

# NODE-07 — Model Provider Matrix

> Phase: 0 Benchmark Before Build  
> Status: **COMPLETE**  
> Implementation Status: **COMPLETE**  
> Implemented Commit: `8f6d2169435e879a1c42ac6d4ba92118f068d0ac`  
> Implementation PR: `#5`  
> Acceptance Report: `reports/nodes/NODE-07/acceptance.md`  
> Clean Acceptance CI: `31654622745`  
> Registry Version: `1.0.0`  
> Observed At: `2026-08-13`  
> Pricing Snapshot Expires: `2026-09-12`  
> Implemented At: `2026-08-13`  
> Priority: P0  
> Depends on: NODE-05, NODE-06  
> Produces: 供应商/模型能力数据库、价格/生命周期快照、任务级候选路由、Live Benchmark 合同

---

## 1. 目标

LUMI 不绑定单一模型。NODE-07 建立可持续更新的 Model Provider Matrix，用官方事实回答“哪些模型具备哪些公开能力、处于什么生命周期、官方如何计价、应进入哪些任务候选集”。

NODE-07 **不提前宣布某个模型最好**。质量、毫秒延迟、真实失败率和实际任务成本必须通过 NODE-05 Benchmark Harness 的 live provider benchmark 才能形成 LUMI 实测数据。

## 2. v1 Provider Scope

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
image generation / image edit
video generation / video edit
text embedding / multimodal embedding
OCR-like multimodal extraction route
structured rerank route
```

## 3. Registry Snapshot

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

Machine-readable source of truth：

```text
docs/models/provider-matrix-manifest.json
docs/models/provider-sources.json
docs/models/route-candidates.json
docs/models/providers/*.json
config/model-registry.seed.json
```

Human-readable matrix：`docs/models/MODEL-PROVIDER-MATRIX.md`。

## 4. Lifecycle Contract

```text
stable      → 可进入 benchmark；通过后可作为 primary/fallback
preview     → 可进入 benchmark；生产路由必须有风险/回退策略
deprecated  → 不可 route eligible
legacy      → 不可 route eligible
shutdown    → 不可 route eligible
```

注册表保留 deprecated sentinel，确保陈旧模型不能误入活跃路由。

## 5. Measurement Truthfulness

无 LUMI live benchmark 时必须保持：

```json
{
  "benchmark_status": "NOT_MEASURED",
  "quality": "NOT_MEASURED",
  "latency_ms": "NOT_MEASURED"
}
```

禁止把供应商 marketing/positioning 转成 LUMI 分数，也禁止在无 Key/预算时伪造延迟或质量排名。

## 6. Price Snapshot Contract

价格记录保留 provider-native unit、USD 值、官方 source、`observed_at`、`pricing_expires_at`。特殊语义不可压平成一个数字：

```text
input/cached/output token
context-length tier
promotion expiry
image output token
per-megapixel/per-image
per-video-second
minimum generation charge
multimodal embedding modality price
```

v1 快照最长使用 30 天，到期必须重新核验。

## 7. Task Routes

当前 15 条候选路由：

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

所有 `selected_primary = null`。候选集合只是 benchmark 输入，不是最终 ranking。

## 8. Live Benchmark Contract

`evals/datasets/model-provider/suite.json` 定义 reasoning、vision/retrieval、image、video、embedding 的任务组。

核心实测 dimensions：

```text
task_success
constraint_success
quality
latency_ms
cost_usd
failure_rate
```

NODE-07 保持：

```text
execution_status = SPECIFIED_NOT_RUN
live_policy = SKIPPED_WITHOUT_PROVIDER_KEY_AND_POSITIVE_BUDGET
```

没有 Provider Key 与明确正数预算时必须 `SKIPPED`，不能 PASS。

## 9. Provider Adapter Contract for NODE-22

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

## 10. Runtime Seed Contract

`config/model-registry.seed.json` 规定：

```text
source of truth = docs/models/providers/*.json
route by capability route name
no application hard-coded provider/model IDs
benchmark required before primary selection
staleness = 30 days
```

NODE-22/23 再把这些合同正规化进入 Model Gateway / Capability Registry。

## 11. CI Contract

```bash
make model-provider-validate
```

`scripts/validate_model_provider_matrix.py` 强制检查：

- 5 Provider / first-party source host；
- 28 models / 27 route eligible；
- 23 stable / 4 preview / 1 deprecated；
- reasoning/image/edit/video/embedding 覆盖；
- active candidate 必须有官方价格；
- inactive lifecycle 不可 route eligible；
- 未实测 quality/latency 必须为 `NOT_MEASURED`；
- preview-only route 必须有 stable fallback；
- live benchmark 前 `selected_primary` 必须为 null；
- 15 route 全部映射 benchmark group；
- live missing credentials/budget 为 SKIPPED contract。

Validator 已接入 blocking `contracts` job，并由 `evals/tests/test_model_provider_matrix_contract.py` 做 Python 回归。

## 12. Clean Acceptance Evidence

Clean PR `#5` / CI `31654622745`：

```text
frontend    PASS
python      PASS — 19 tests; Pyright 0 errors / 0 warnings
contracts   PASS
integration PASS
eval-smoke  PASS
secret-scan PASS — run 31654622779
dependency review PASS — run 31654622764
```

Registry validator exact contract：

```text
providers=5 models=28 route_eligible=27
lifecycle=stable:23, preview:4, deprecated:1
official_sources=30 routes=15
benchmark_status=NOT_MEASURED:28
no provider winner selected before LUMI live benchmark
```

详细证据见 `reports/nodes/NODE-07/acceptance.md`。

## 13. 验收标准

- [x] reasoning/image/video/embedding 与 edit 覆盖。
- [x] 至少五家 Provider。
- [x] 能力/价格/lifecycle 有时间戳和 first-party source。
- [x] 建立 15 个任务级候选路由。
- [x] preview lifecycle 有稳定回退规则。
- [x] 无 live benchmark 时真实值为 `NOT_MEASURED`。
- [x] Provider Adapter contract 可支持 NODE-22。
- [x] Live suite 无 Key/预算时必须 SKIPPED。
- [x] Registry validator 接入 CI contracts。
- [x] Implementation PR 完整 NODE-04/05/06 gates 全绿并归档。

## 14. Definition of Done

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
clean implementation PR validation      PASS
implementation merged to main           PASS
```

下一节点：NODE-08 Canvas Technology Spike。

# NODE-22 — Model Gateway

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-07, NODE-20, NODE-27(spec dependency completed within phase)  
> Produces: 统一模型调用入口、Provider Adapter、routing/fallback、usage/cost telemetry

---

## 1. 目标

所有 LLM/Image/Video/Embedding/OCR 等模型调用统一经过 Model Gateway。Agent、API 和 Worker 不直接 import provider SDK，不把 provider-native schema 扩散到领域层。

## 2. 逻辑架构

```text
Caller
  ↓
ModelRequest
  ↓
Capability Resolver
  ↓
Routing Policy
  ↓
Budget / Health / Quota Guard
  ↓
Provider Adapter
  ↓
Provider API
  ↓
Normalized Result + Usage + Cost
```

## 3. ModelRequest

统一 contract：

```text
request_id
organization_id
project_id?
task_id?
operation_id
capability
quality_profile
latency_profile
budget_limit
inputs
structured_output_schema?
reference_assets[]
constraints
routing_hints
```

调用方表达“要什么能力”，不直接指定 provider-native 参数。高级用户可有 model preference，但仍经过政策校验。

## 4. Capability Examples

```text
llm.reasoning
llm.structured_output
llm.vision
image.generate
image.edit
image.mask_edit
image.reference_consistency
image.transparent_background
video.text_to_video
video.image_to_video
embedding.text
embedding.multimodal
ocr.document
```

## 5. Provider Adapter

```python
class ProviderAdapter:
    capabilities()
    validate(request)
    estimate_cost(request)
    invoke(request)
    get_async_status(provider_request_id)
    cancel(provider_request_id)
    normalize_error(error)
```

异步视频/图像 provider 可返回 `PENDING` + provider_request_id，由 worker poll/webhook adapter 收敛。

## 6. Normalized Result

```text
status
provider
model
provider_request_id
outputs[] -> Asset/temporary refs
usage
timing
safety_metadata
finish_reason
raw_response_ref? (restricted)
```

原始响应仅在 debug/法律允许范围内受控保存，不直接返回 Web。

## 7. Routing

输入：

```text
required capabilities
quality threshold
constraint profile
budget
provider health
latency target
organization policy
region/legal policy
```

输出有序候选：

```text
primary
fallback_1
fallback_2
```

Router 必须可解释，记录 `routing_reason_codes`。

## 8. Fallback

只对可 fallback 的 error：

```text
RATE_LIMIT
TIMEOUT
PROVIDER_5XX
CAPABILITY_TEMP_UNAVAILABLE
```

通常不 fallback：

```text
AUTH_ERROR
INVALID_REQUEST
USER_CONTENT_POLICY_BLOCK
BUDGET_EXCEEDED
HARD_CONSTRAINT_INVALID
```

否则会通过换 provider 绕过应有政策。

## 9. Retry

单 provider retry 与 cross-provider fallback 分离。

- exponential backoff + jitter；
- obey Retry-After；
- retry count/elapsed budget；
- paid generation 前接 NODE-20 idempotency/reconciliation。

## 10. Cost

调用前：estimate + reserve budget。

调用后：actual usage → NODE-27 cost ledger。

如果 provider 不返回精确 usage，使用 price snapshot +可验证计量估算，并标 `cost_confidence`。

## 11. Prompt Boundary

Prompt Compiler 在 Context 层；Gateway 可以做 provider-format adapter，但不负责业务 Prompt 创意。

```text
Compiled Prompt
→ Provider Formatter
→ API request
```

## 12. Streaming

LLM streaming：Gateway 输出标准 chunk event；不得把 provider-specific chunk class 泄漏给 LangGraph/Web。

图像/视频 long job 通过 job status/realtime event，不伪装 token stream。

## 13. Secrets

Provider keys 只存在 Gateway secret scope；Agent Runtime 与 Sandbox 不持有。

按 provider/environment 独立 secret name，支持 rotation。

## 14. Observability

记录：

```text
model_request_id
provider/model
capability
routing reasons
latency
TTFT if applicable
usage
cost
retry/fallback
error category
trace id
```

不得默认 log 完整 prompt/用户图片 URL。

## 15. MockProvider

无真实 Key 也必须能：

- deterministic LLM structured response；
- fake image asset fixture；
- async fake video；
- simulated 429/timeout/5xx。

支持所有 CI/integration。

## 16. Tests

- route by capability；
- budget filter；
- health filter；
- fallback allowed/not allowed；
- stream normalize；
- async provider lifecycle；
- idempotent paid request；
- secret not exposed；
- MockProvider deterministic。

## 17. 验收标准

- [ ] 至少 2 个 LLM adapter 或 1 real + 1 mock。
- [ ] 至少 image provider contract 可插拔。
- [ ] Agent 不 import provider SDK。
- [ ] routing/fallback 有测试。
- [ ] cost/usage 上报。
- [ ] provider key 只在 Gateway。
- [ ] 错误统一 taxonomy。

## 18. Definition of Done

```text
Gateway API + client committed
+ adapters green
+ routing/fallback eval green
+ mock mode full CI green
```

下一节点：NODE-23 Capability Registry。

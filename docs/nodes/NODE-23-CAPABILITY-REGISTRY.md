# NODE-23 — Capability Registry

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-07, NODE-22  
> Produces: 可版本化模型能力/限制/质量/价格元数据注册中心

---

## 1. 目标

让 Router 基于结构化事实做决策，而不是 `if task == image: model_x`。Registry 是 Model Gateway 的控制面数据，不承担实际调用。

## 2. Entities

```text
Provider
ModelDefinition
ModelRevision/Snapshot
Capability
CapabilityClaim
PricingSnapshot
BenchmarkScore
RoutingProfile
OrganizationModelPolicy
```

## 3. Capability Claim

```yaml
model_key: provider:model
capability: image.edit
support: full|partial|none|unknown
limits:
  max_input_images: 4
  output_formats: [png]
confidence: verified_docs|live_test|inferred
observed_at: "..."
source_ref: "..."
```

`unknown` 不能被当作 false，也不能被 Router 当 full。

## 4. Quality Scores

按 benchmark profile：

```text
planning
structured_ir
chinese_copy
image_text_fidelity
product_identity
image_edit_precision
video_motion
```

记录 dataset version、run id、样本数和 confidence interval/统计信息；禁止只存一个神秘总分。

## 5. Pricing Snapshot

```text
provider
model
region?
currency
unit
price
minimum_charge?
effective_from
observed_at
source
```

历史 snapshot 保留，以便解释旧 Cost Ledger。

## 6. Routing Profile

示例：

```yaml
profile: image-edit-precision
required:
  - image.edit
weights:
  quality: 0.45
  constraint: 0.30
  cost: 0.10
  latency: 0.10
  availability: 0.05
minimum:
  quality: 80
```

## 7. Update Strategy

P0：registry seed YAML + DB snapshot。

实施 Node-07 调研生成 seed；启动时加载/迁移。后台管理后续允许安全更新，但生产修改必须 versioned/audited。

## 8. Hot Reload

Model Gateway 可缓存 registry；变更通过 version/event 失效。请求开始后固定此次 route snapshot，不能中途因为 registry 变化导致 provenance 不可解释。

## 9. Organization Policy

支持：

```text
disabled providers
allowed regions
max cost class
preferred models
data handling restrictions
```

企业组织可禁止某 provider。

## 10. Validation

Registry 启动检查：

- model adapter 存在；
- required provider secret configuration readiness；
- capability claim schema；
- pricing units；
- routing profile weights；
- fallback candidate 至少有一个（若业务要求）。

## 11. API/Internal Query

```text
list_models(capability, policy)
get_model_snapshot(model_key)
rank_candidates(profile, request_context)
get_pricing(model_key, at_time)
```

公开 API 不暴露 provider Secret 或内部健康细节。

## 12. Tests

- unknown capability；
- partial support filter；
- expired price；
- org blocked provider；
- benchmark version comparison；
- cache invalidation；
- provenance snapshot stability。

## 13. 验收标准

- [ ] model/capability/pricing/benchmark 分表或分实体。
- [ ] observed_at/source/confidence 必备。
- [ ] Router 从 Registry 查询，不硬编码模型。
- [ ] org policy 能过滤候选。
- [ ] 历史 pricing 可查询。

## 14. Definition of Done

```text
registry schema + seed committed
+ routing profile evaluator green
+ cache/version behavior green
```

下一节点：NODE-24 Provider Health。

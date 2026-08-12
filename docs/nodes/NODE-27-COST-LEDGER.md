# NODE-27 — Cost Ledger, Budget & Quota Foundation

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / FINANCIAL  
> Depends on: NODE-10, NODE-20, NODE-22, NODE-23  
> Produces: provider cost ledger、预算 reservation、usage aggregation、quota guard

---

## 1. 目标

保证 LUMI 知道每次 Agent/Model/Tool/Artifact 实际花了多少钱，并能在任务执行前阻止明显超预算。这里先做“成本与用量真相”，客户 Billing/支付在 NODE-63。

## 2. 核心原则

1. 金额使用 Decimal/numeric，不用 float。
2. Ledger entry immutable。
3. Provider cost 与 customer charge 分离。
4. Estimate、Reserve、Actual 分离。
5. 每条成本能追到 operation/generation/provider request。

## 3. Ledger Entry

```text
id
organization_id
project_id?
task_id?
agent_run_id?
generation_id?
operation_id?
provider
model
entry_type
amount
currency
quantity
unit
pricing_snapshot_id
provider_request_id?
confidence
occurred_at
metadata
```

`entry_type`：

```text
ESTIMATE
RESERVATION
ACTUAL_COST
RESERVATION_RELEASE
ADJUSTMENT
REVERSAL
```

Estimate 可不进正式不可变财务 ledger，也可单独表；Actual/adjustment 必须不可变。

## 4. Budget Hierarchy

```text
Organization monthly
→ Project budget
→ AgentRun budget
→ Task budget
→ Operation budget
```

下层不能无授权超过上层剩余预算。

## 5. Reservation Flow

```text
Gateway estimate
→ atomically reserve
→ invoke paid provider
→ actual usage
→ record actual
→ release remaining reservation
```

超出 estimate 时按 policy：允许小容差、请求升级、或终止后续 steps。

## 6. Pricing

使用 NODE-23 PricingSnapshot。每次 actual entry 保存 snapshot id，后续价格更新不改历史。

## 7. Currency

Provider 原币记录；聚合报表可转换 display currency。汇率 snapshot 与 provider price 类似需要时间戳；P0 可统一 USD provider cost 后再扩展。

## 8. Usage Units

支持：

```text
input_tokens
output_tokens
images
megapixels
seconds_video
seconds_audio
requests
storage_bytes_month (后续)
```

不要假定所有 provider 都按 token。

## 9. Unknown Cost

Provider 无即时价格/usage：记录 estimated actual + `confidence=ESTIMATED`，后台 reconciliation 后用 ADJUSTMENT，不修改旧 row。

## 10. Quota

P0 quota guard：

```text
monthly provider cost cap
per-run budget
concurrent generation cap
asset storage cap hook
```

quota 不是账单支付；只是允许使用多少资源。

## 11. Router Integration

Router 接收：

```text
remaining_budget
candidate estimated_cost
quality target
```

可选择较低成本候选或减少 variants，但不得偷偷降低用户明确的 hard quality constraint；要产生 decision trace。

## 12. Cost Allocation

一个 provider call 必须精确归属主要 Task/AgentRun。共享请求可以用 allocation entries，但禁止“无法解释的 global cost”。

## 13. APIs

```text
GET /usage
GET /costs/summary
GET /projects/{id}/costs
```

普通用户看到聚合；Admin 可查看 provider-level，权限受控。

## 14. Alerts

```text
50%/80%/100% project budget
monthly org threshold
abnormal cost spike
unknown cost reconciliation backlog
```

## 15. Tests

- decimal precision；
- concurrent reservation；
- idempotent actual；
- reservation release；
- adjustment/reversal；
- pricing snapshot historical；
- budget hierarchy；
- provider retry 不 double charge。

## 16. 验收标准

- [ ] 每个 paid generation 可追成本。
- [ ] 同 operation 不重复 actual。
- [ ] reservation 防并发超卖预算。
- [ ] history pricing 可解释。
- [ ] provider cost/customer billing 分离。
- [ ] Router 可读取预算。

## 17. Definition of Done

```text
cost ledger implemented
+ reservation concurrency green
+ gateway integration green
+ cost summary API green
```

完成 Phase 3，下一节点：NODE-28 LangGraph Control Plane。

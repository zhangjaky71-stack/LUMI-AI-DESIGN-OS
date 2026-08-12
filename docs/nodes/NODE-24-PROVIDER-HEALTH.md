# NODE-24 — Provider Health & Circuit Breaker

> Phase: 3 AI Infrastructure  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / RELIABILITY  
> Depends on: NODE-22, NODE-23  
> Produces: Provider/Model 健康状态、熔断、降级与 synthetic probe

---

## 1. 目标

第三方 AI provider 必然会限流、超时、5xx 或局部模型不可用。Router 需要实时健康信号避免把所有请求持续打到故障服务。

## 2. Health Scope

至少两层：

```text
provider health
model/capability endpoint health
```

同 provider 的 LLM 正常不代表 video endpoint 正常。

## 3. Signals

被动：

```text
success/failure rate
429 rate
5xx rate
timeout rate
latency P50/P95
queue/poll completion time
```

主动 synthetic：低成本/无副作用 probe，仅在 provider 条款允许时。

## 4. States

```text
UNKNOWN
HEALTHY
DEGRADED
OPEN_CIRCUIT
RECOVERING
DISABLED
```

`DISABLED` 是人工/政策状态，不由自动 health 恢复。

## 5. Circuit Breaker

使用 rolling window + minimum sample，避免少量偶发失败误熔断。

```text
CLOSED
→ threshold breached
OPEN
→ cooldown
HALF_OPEN
→ probe samples
CLOSED or OPEN
```

参数按 provider/capability profile 配置。

## 6. 错误归因

以下不应降低 provider health：

```text
user content blocked
invalid user input
org budget exceeded
our own schema bug
```

只使用 provider/transport attributable errors。

## 7. Rate Limit

捕获 provider response headers（受支持时）并维护短期 capacity hints。Router 可降低并发/切换，而不是等 429 洪峰。

## 8. Health Store

Redis 适合短期 window/circuit state；定期 summary 持久化 DB/metrics。Redis 丢失时状态回 UNKNOWN，不导致业务真相损坏。

## 9. Router Integration

候选排名：

```text
DISABLED/OPEN → exclude
DEGRADED → penalty
UNKNOWN → allow with conservative policy
HEALTHY → normal
```

若全部不可用，返回明确 `MODEL_CAPABILITY_TEMPORARILY_UNAVAILABLE`。

## 10. Manual Override

Admin 可：

```text
disable model/provider
force degraded
clear breaker
```

必须 Audit + TTL/explicit reason，避免永久忘记 override。

## 11. Metrics/Alert

```text
provider_success_rate
provider_p95_latency
provider_429_rate
provider_circuit_state
fallback_rate
all_candidates_unavailable_total
```

关键 capability 全不可用立即告警。

## 12. Tests

- 5xx burst opens；
- user 400 不 opens；
- half-open recovery；
- multiple capabilities isolated；
- manual disable；
- Redis reset；
- Router fallback。

## 13. 验收标准

- [ ] health state 可查询。
- [ ] 熔断与恢复可测试。
- [ ] 非 provider 错误不污染健康。
- [ ] Router 使用健康状态。
- [ ] manual override 可审计。

## 14. Definition of Done

```text
health collector + breaker implemented
+ failure injection green
+ router degradation green
```

下一节点：NODE-25 Tool Gateway。

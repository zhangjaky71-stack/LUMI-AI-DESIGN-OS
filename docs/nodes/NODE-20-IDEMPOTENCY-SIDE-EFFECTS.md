# NODE-20 — Idempotency & Side Effect Gateway

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / RELIABILITY / COST  
> Depends on: NODE-10, NODE-19, NODE-15  
> Produces: Idempotency service、operation ledger、paid side-effect guard、recovery protocol

---

## 1. 目标

LangGraph resume、worker retry、网络 timeout、客户端重复点击都可能重复执行。LUMI 必须保证“重复 command 不导致重复收费/重复生成/重复写关键结果”。

这是 application-level guarantee，不宣称分布式环境绝对 exactly-once。

## 2. Side Effects 范围

必须过 Gateway：

```text
paid model invocation
image/video generation
external tool write
object finalization
billing charge/credit
email/invite send where duplication matters
export creation
external publish
```

纯读请求不需要。

## 3. Idempotency Key

HTTP 客户端：`Idempotency-Key`。

内部 operation：

```text
organization_id
operation_type
business_scope_id
deterministic operation key
```

例如 generation：

```text
project + task + logical_generation_slot + attempt_policy_version
```

不要把随机 retry attempt 作为新业务 key。

## 4. Record

```text
id
organization_id
idempotency_key
operation_type
request_hash
status
lease_owner
lease_expires_at
provider_request_id
result_ref
response_status
error_category
created_at
completed_at
```

Unique：`(organization_id, operation_type, idempotency_key)`。

## 5. Request Hash

同一个 key + 不同语义 request：返回 `409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`，不能返回旧结果造成逻辑错乱。

Hash 使用 canonical normalized request，不含瞬时 trace id。

## 6. State Machine

```text
NEW → IN_PROGRESS → SUCCEEDED
                 ↘ FAILED_RETRYABLE
                 ↘ FAILED_FINAL
```

过期 lease 可被 recovery worker 重新 claim，但先做 provider reconciliation。

## 7. Provider Reconciliation

最危险窗口：

```text
provider accepted job
→ process crashes
→ DB not marked success
```

恢复时：

1. 若已有 provider_request_id，查询 provider status（若 API 支持）；
2. 若结果已生成，收敛到同一 operation；
3. 不支持查询时使用 provider-native idempotency 功能（若有）或保守人工/retry policy；
4. 记录 ambiguity，不静默重复付费。

## 8. Response Replay

HTTP 相同请求完成后重试：

- 返回等价业务 response；
- 不重复执行；
- 可标 header `Idempotent-Replayed: true`。

大 response 存 `result_ref`，不一定整包 DB。

## 9. DB Transaction Side Effects

数据库内 side effect 优先 transaction + unique constraint。不要用 Redis lock 替代 DB uniqueness。

Redis lock 可降低竞争，但不是最终 correctness boundary。

## 10. LangGraph 规则

所有 interrupt 前发生的 side effect 必须幂等，因为 resume 可能重新进入节点逻辑。Graph node 中调用 SideEffectGateway，不直接 provider SDK。

## 11. Compensation

不是所有外部操作可 rollback。定义：

```text
COMPENSATABLE
NON_COMPENSATABLE
REVERSIBLE_BY_NEW_OPERATION
```

例如 credits ledger 用 reversal entry，不修改旧 entry。

## 12. Metrics

```text
idempotency_replay_total
idempotency_conflict_total
stale_lease_total
provider_reconciliation_total
duplicate_prevented_total
ambiguous_side_effect_total
```

`ambiguous_side_effect_total > 0` 触发告警。

## 13. Failure Injection Tests

必须模拟：

1. provider success 后 DB commit 前 crash；
2. client timeout 后重复 POST；
3. worker crash；
4. LangGraph interrupt/resume；
5. broker duplicate；
6. same key different request；
7. two concurrent same key。

## 14. 验收标准

- [ ] 同 key concurrent request 只产生一次业务 operation。
- [ ] completed request 可 replay。
- [ ] same key/different body 被拒绝。
- [ ] provider crash window 有 reconciliation。
- [ ] paid side effect 全部走 gateway。
- [ ] Cost Ledger 不出现重复 charge。
- [ ] failure injection suite 通过。

## 15. Definition of Done

```text
idempotency gateway implemented
+ concurrency tests green
+ crash-window tests green
+ provider reconciliation contract ready
```

下一节点：NODE-21 Sandbox Runtime。

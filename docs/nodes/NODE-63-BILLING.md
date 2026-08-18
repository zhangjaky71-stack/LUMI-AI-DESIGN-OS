# NODE-63 — Billing, Plans, Credits & Payment Integration

> Phase: 8 SaaS & Collaboration  
> Status: CORE IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P1 / COMMERCIALIZATION  
> Depends on: NODE-16, NODE-27, NODE-20  
> Produces: Plan/Entitlement、Credits、Subscription、PaymentProvider Adapter、Webhook幂等与账单UX

---

## 1. 目标

把内部真实 Provider Cost 转换成可商业化的套餐、额度、订阅和客户收费系统，同时把支付卡数据留给合规支付Provider，不让 LUMI 自己处理敏感卡号。

## 2. 严格区分

```text
Provider Cost Ledger  = LUMI付给AI/基础设施的成本
Customer Usage        = 用户消耗的产品单位
Customer Billing      = 用户应付金额/订阅
Credits/Entitlements  = 产品使用权
```

NODE-27是真实成本基础；NODE-63不能覆盖它。

当前实现增加 `PostgresBillingReconciliationService`，只读 `cost_ledger` 与 Billing invoice reference 做对账；Billing 代码禁止 INSERT/UPDATE `cost_ledger`。

## 3. Domain

```text
Plan
PlanVersion
Entitlement
Subscription
BillingAccount
CreditWallet
CreditLedger
InvoiceRef
PaymentCustomerRef
PaymentEvent
```

已落地 PostgreSQL tables：

```text
billing_plans
billing_plan_versions
billing_accounts
billing_subscriptions
billing_credit_wallets
billing_credit_ledger
billing_invoice_refs
billing_payment_events
```

Migration chain：`20260818_0022 -> 20260818_0023`。

## 4. Plan Versioning

套餐变价/变权益创建新PlanVersion。已有subscription保留其price/entitlement策略直到迁移。

NODE-63 core 已增加 database trigger：PlanVersion 的价格、included credits、entitlements、pricing policy、effective time 等 material fields 不允许原地修改；退休时间可单独更新。已有 subscription 永远 pin `plan_version_id`。

## 5. Entitlements

例如：

```text
monthly credits
max concurrent generations
max projects/storage
video enabled
team seats
brand kits
priority routing
```

功能代码查询 entitlement snapshot，不散落 `if plan == pro`。

当前 normalized subscription policy：

- `TRIALING / ACTIVE / PAST_DUE`：保留 pinned PlanVersion entitlements；
- `CANCEL_AT_PERIOD_END`：在 current period end 前保留，期满撤销；
- `CANCELLED / INCOMPLETE`：撤销 paid entitlements。

真正昂贵任务的 runtime gate 仍需把 Entitlement/Credit preflight 接进 generation/tool gateways，见 P0 gap。

## 6. Credits

Credit Ledger immutable：

```text
GRANT
CONSUME
REFUND
EXPIRE
ADJUSTMENT
REVERSAL
```

余额是ledger projection，`billing_credit_wallets.cached_balance` 只是缓存投影。

已实现：

- `billing_credit_ledger` UPDATE/DELETE database trigger fail-closed；
- 每组织 `operation_id` 唯一，retry 不重复扣/发；
- wallet row `SELECT ... FOR UPDATE`；
- 非明确 postpaid contract 时 balance 不得小于0；
- refund 追加 `REFUND` entry，不修改旧 `CONSUME`。

真实双连接并发 race test 仍必须在 Hosted/PostgreSQL 执行后才可把并发验收标记 complete。

## 7. Usage Conversion

Provider cost与credits不是1:1。建立 versioned pricing policy：

```text
image generation = N credits/profile
video second = ...
premium model multiplier
```

`BillingService.price_usage()` 从 PlanVersion `pricing_policy_json` 读取 rate + policy version，禁止 float 计价；Provider Cost 仍独立来自 NODE-27。

目前 conversion service 已落地，但 runtime generation/tool 的 pre-reserve/consume wiring 仍是 P0。

## 8. Payment Provider Adapter

Adapter contract：

```text
create_customer
create_checkout/subscription
create_portal_session
verify_webhook
```

NODE-63 首个实现为 `MockPaymentProvider`：

- hosted checkout/portal URL；
- HMAC-SHA256 webhook signature；
- `hmac.compare_digest` constant-time compare；
- normalized PaymentEvent；
- webhook 中发现 PAN/card_number/CVC/CVV/track-data 类字段直接拒绝。

真实支付Provider必须等 sandbox acceptance 后再接，不在本节点假装已完成商户开户/API Key/生产支付。

## 9. Webhooks

支付Provider是异步真相之一：

```text
verify signature
→ persist provider_event_id + body_sha256
→ idempotency
→ normalize event
→ transaction update subscription/invoice/credit
→ mark applied
```

核心防线：

- `(provider, provider_event_id)` unique；
- 相同 event id 若 body hash 不同，conflict；
- credit grant operation UUID 从 provider/event id deterministic derivation；
- duplicate applied event 直接返回 prior status，不重复发 credits；
- webhook route 不依赖浏览器 user auth，只依赖 Provider signature；
- 产品 Billing routes 仍受 `enforce_api_auth` + RBAC 保护。

## 10. Subscription States

内部normalize：

```text
TRIALING
ACTIVE
PAST_DUE
CANCEL_AT_PERIOD_END
CANCELLED
INCOMPLETE
```

Provider-specific更多状态不扩散到业务域。

## 11. Billing UX

目标：

- current plan；
- usage/credits；
- invoices link；
- upgrade/downgrade；
- payment portal；
- seats P1。

当前 API 已提供 overview / entitlements / credits / invoices / checkout / portal。支付页只返回 hosted URL，LUMI 不接触卡号。

Plan catalog 管理、upgrade/downgrade catalog UX 与 seats 仍留给商业/Admin Console 后续节点。

## 12. No Negative Surprise

Repository 已实现原子余额检查，非 `postpaid_allowed` 套餐不能把 wallet 扣成负数。下一步必须把这个能力接到 image/video/tool 等昂贵任务 **开始前**，而不是任务执行后再扣费。

## 13. Refund / Adjustment

失败生成是否退credit由versioned policy决定；使用ledger `REFUND/ADJUSTMENT`，不改旧 `CONSUME`。

## 14. Tax / Invoice

税务计算和正式invoice交支付Provider/税务服务；LUMI只保存reference/status/hosted invoice URL。不同国家法规实施前需法务/会计核验，代码不硬编码税率。

## 15. Tests

NODE-63 acceptance suite 覆盖/约束：

- Mock webhook signature valid/invalid；
- webhook card-data rejection；
- normalized subscription states；
- entitlement snapshot + cancelled transition；
- versioned credit pricing；
- billing.read permission；
- repository `FOR UPDATE` / insufficient-credit fence；
- payment event/body hash idempotency contract；
- migration immutable ledger + immutable material plan version；
- Cost Ledger read-only reconciliation；
- public signed webhook 与 authenticated Billing API composition 分离。

仍待 Hosted 真实执行：

- two-connection concurrent credit consume；
- full PostgreSQL migration `0023`；
- compile/pytest/ruff/typecheck；
- Web build（如 Billing UI surface 纳入本节点）。

## 16. 验收标准

- [x] Mock支付核心流程可在无真实商户情况下开发。
- [x] Payment webhook schema/idempotency/body-conflict fence 已实现。
- [x] Credits immutable ledger schema + repository 已实现。
- [x] Entitlement不靠plan名称散落判断。
- [x] Hosted checkout/portal，用户卡数据不进入 LUMI business API。
- [x] Provider cost与Customer billing有独立只读 reconciliation projection。
- [ ] Hosted PostgreSQL migration/test evidence。
- [ ] Live concurrent consume race test。
- [ ] Generation/tool runtime preflight/consume wiring。
- [ ] Production service factory/provider secret composition。

## 17. 当前 P0 Gaps

以 `reports/nodes/NODE-63/gap-ledger.json` 为准：

1. production `billing_service_factory` composition；
2. generation/tool runtime credits preflight/consume；
3. live PostgreSQL concurrent-consume race test；
4. Hosted compile/test/migration/lint evidence。

Real Payment Provider、tax、seat billing、plan admin catalog 属 P1，且 Real Provider 必须在 sandbox acceptance 后实施。

## 18. Definition of Done

```text
billing domain + mock provider implemented
+ webhook/idempotency/credit tests green
+ live concurrency proof
+ runtime credit gate wired
+ production billing composition verified
+ real provider only after sandbox acceptance
```

当前结论：`CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE`。

下一节点：NODE-64 Admin Console。

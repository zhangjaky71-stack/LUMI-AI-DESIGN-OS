# NODE-63 — Billing, Plans, Credits & Payment Integration

> Phase: 8 SaaS & Collaboration  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
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

## 4. Plan Versioning

套餐变价/变权益创建新PlanVersion。已有subscription保留其price/entitlement策略直到迁移。

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

功能代码查询EntitlementService，不散落 `if plan == pro`。

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

余额是ledger projection，可缓存但可从ledger重建。

## 7. Usage Conversion

Provider cost与credits不是1:1。建立 versioned pricing policy：

```text
image generation = N credits/profile
video second = ...
premium model multiplier
```

产品可平滑成本波动；实际毛利仍用Provider Cost对比Customer Revenue。

## 8. Payment Provider Adapter

```text
create_customer
create_checkout/subscription
create_portal_session
get_subscription
cancel/update
verify_webhook
```

首个实现可选成熟支付服务；具体账户/API Key在实施时由用户完成无法代办的商户开通。工程先以 MockPaymentProvider完成全部流程。

## 9. Webhooks

支付Provider是异步真相之一：

```text
verify signature
→ persist raw event ref/hash
→ idempotency by provider_event_id
→ normalize event
→ transaction update subscription/invoice
→ audit
```

重复webhook不能重复发credits。

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

Provider-specific更多状态保存在metadata，不泄漏业务所有地方。

## 11. Billing UX

- current plan；
- usage/credits；
- invoices link；
- upgrade/downgrade；
- payment portal；
- seats P1。

支付页优先跳Hosted Checkout/Portal，减少PCI范围。

## 12. No Negative Surprise

昂贵任务在额度不足前阻断/提示；不允许任务完成后才发现账户余额负数，除明确enterprise postpaid contract。

## 13. Refund / Adjustment

失败生成是否退credit由versioned policy决定；使用ledger REFUND/ADJUSTMENT，不改旧CONSUME。

## 14. Tax / Invoice

税务计算和正式invoice尽量交支付Provider/税务服务；LUMI保存references/status。不同国家法规实施前需法务/会计核验，不在代码里硬编码税率。

## 15. Tests

- subscription create/mock；
- duplicate webhook；
- signature invalid；
- credit concurrent consumption；
- refund；
- plan version change；
- insufficient credits；
- cancelled subscription entitlement transition。

## 16. 验收标准

- [ ] Mock支付完整E2E，无真实商户也能开发。
- [ ] Payment webhook幂等。
- [ ] Credits immutable ledger。
- [ ] Entitlement不靠plan名称散落判断。
- [ ] 用户卡数据不经过LUMI业务后端。
- [ ] Provider cost与Customer billing可对账。

## 17. Definition of Done

```text
billing domain + mock provider implemented
+ webhook/idempotency/credit tests green
+ real provider only after sandbox acceptance
```

下一节点：NODE-64 Admin Console。

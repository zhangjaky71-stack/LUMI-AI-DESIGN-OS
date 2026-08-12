# LUMI AI Design OS — Node Implementation Protocol

> Purpose: 将已经完成的 NODE-00～73 详细规格转化为可审计的工程实施流程。

---

## 1. 一个 Node 的标准生命周期

```text
SPECIFIED
  ↓
DEPENDENCY CHECK
  ↓
IN_PROGRESS
  ↓
IMPLEMENTED
  ↓
VALIDATING
  ↓
COMPLETE
```

不允许从 `SPECIFIED` 直接改为 `COMPLETE`。

## 2. 开始前

执行者必须：

1. 阅读该 Node 全文。
2. 阅读直接依赖 Node 的最终实现状态和 ADR。
3. 检查当前 repo/branch/CI。
4. 将 Node Acceptance Criteria 转成可运行测试清单。
5. 识别需要真实外部账号的项目，并提前准备 Mock Adapter。

## 3. 实现过程中

原则：

```text
contract first
deterministic first
security server-side
mockable external providers
no secrets in git
no silent architecture drift
```

所有新的 provider/tool/agent/schema 都要通过 Registry/Adapter/Contract，不允许在业务代码里临时硬编码绕过Gateway。

## 4. 最低测试要求

每个Node按自身文档执行，并至少覆盖：

```text
happy path
invalid input
authorization/tenant where relevant
concurrency/idempotency where relevant
provider/network failure where relevant
restart/recovery where relevant
contract/schema
regression
```

只有UI文档也必须有E2E/interaction tests，不能只截一张图验收。

## 5. 外部依赖原则

用户无法提供商业账号/Key时：

```text
Mock Provider
Local Emulator
Recorded Fixture
Test/Sandbox Adapter
```

继续完成所有可完成工程。

只有如下不可代理动作记录 `BLOCKED_EXTERNAL`：

```text
commercial API account approval
cloud payment/account identity verification
domain ownership/purchase
payment merchant onboarding
enterprise licenses
legal/compliance sign-off
```

## 6. Acceptance Evidence

每Node建立（需要时）：

```text
reports/nodes/NODE-XX/
├─ acceptance.md
├─ test-results.*
├─ benchmark.*
├─ screenshots/       # UI场景
├─ traces/            # sanitized references
└─ known-limitations.md
```

证据不得包含Secret或真实客户敏感数据。

## 7. Definition of Complete

必须全部满足：

```text
implementation exists
+ relevant tests pass
+ acceptance criteria pass
+ docs match implementation
+ security implications reviewed
+ CI green
+ GitHub commit pushed
+ NODE-INDEX updated
```

否则仍为 `IN_PROGRESS` / `VALIDATING`。

## 8. Failure Policy

测试失败时不能通过删除测试/降低门槛伪装成功。若门槛确实不合理：

```text
evidence
→ ADR/change proposal
→ update spec/benchmark with rationale
→ rerun
```

## 9. Architecture Drift

以下视为高风险 drift：

- Agent直接调用Provider SDK绕Model Gateway。
- Agent直接访问数据库/Host Shell。
- Prompt代替Tool permission/Constraint enforcement。
- Canvas/Pixi对象成为持久化Domain模型。
- Redis成为Project/Cost/Artifact唯一真相源。
- Artifact approved version被原地修改。
-付费操作没有幂等Operation。
- cross-tenant query不带tenant scope。

发现时停止该实现，创建ADR或修回Architecture V2。

## 10. Node Commit

推荐：

```text
feat(scope): implement <capability> (NODE-XX)
```

提交说明包含：

```text
What
Why
Tests
Acceptance
Known limitations
```

## 11. Node Completion Update

对应Node文档顶部增加：

```text
Implementation Status: COMPLETE
Implemented Commit: <sha>
Acceptance: reports/nodes/NODE-XX/acceptance.md
```

`docs/NODE-INDEX.md` 同步改状态。

## 12. Phase Gate

一个Phase全部Node COMPLETE后，运行该阶段跨Node E2E，再进入下一Phase。尤其：

```text
Phase 0 → Benchmark ready
Phase 1 → Contracts frozen
Phase 2 → Runtime correctness/security
Phase 3 → AI infrastructure routing/cost
Phase 4 → Agent mock E2E
Phase 5 → Design IR/Canvas/Artifact E2E
Phase 6 → Generate/Edit/QA E2E
Phase 7 → Frontend E2E
Phase 8 → SaaS/Governance E2E
Phase 9 → Production acceptance
```

## 13. 最终原则

文档的作用不是“看起来完整”，而是让每一项工程都有明确输入、输出、失败条件和验收证据。后续实现严格以 `docs/NODE-INDEX.md` 为入口，以每个 `docs/nodes/NODE-XX-*.md` 为施工单。

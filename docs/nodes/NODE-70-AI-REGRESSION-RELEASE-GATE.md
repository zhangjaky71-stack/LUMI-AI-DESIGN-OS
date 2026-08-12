# NODE-70 — AI Regression, Experiment & Release Gate

> Phase: 9 Production Readiness  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / AI RELEASE BLOCKER  
> Depends on: NODE-05, NODE-23, NODE-30～32, NODE-46～51, NODE-67  
> Produces: Production Baseline、Candidate比较、Shadow/Canary、Agent/Prompt/Model/Skill/Recipe发布门禁

---

## 1. 目标

模型、Prompt、Agent、Skill和Recipe每次更新都可能“看起来更聪明但实际某类任务变差”。建立统一AI release process，任何生产别名切换必须有Benchmark证据。

## 2. Versioned Candidates

Release unit可包含：

```text
agent version
system prompt/template hash
skill versions
recipe version
model routing policy
critic version
constraint thresholds
context policy
```

必须保存完整candidate manifest。

## 3. Baseline

Production运行版本形成immutable baseline manifest。每次评测：

```text
candidate vs exact production baseline
```

不是跟“上次我电脑上跑的结果”比。

## 4. Eval Suites

Blocking核心：

```text
brief extraction
planning/task graph
tool permission
Design IR validity
constraint following
local edit golden cases
brand consistency
identity
visual critic
recovery/idempotency
cost
latency
security agent red-team
```

图片/视频主观质量另有人评/pairwise。

## 5. Statistical Rules

报告至少包含样本量、均值/成功率、差异和置信信息。小样本不能因为+2分就宣称显著提升。

## 6. Guardrails

绝不允许回归：

```text
critical security/safety
cross-tenant/tool permission
duplicate paid side effect
hard constraint golden suite
schema validity
```

质量项设置容差；成本/延迟也有上限。

## 7. Shadow

对于可安全shadow的真实生产输入：

-复制脱敏/授权输入给candidate；
- candidate结果不展示/不产生外部side effect；
- 付费成本有预算；
- 数据政策允许。

不能shadow destructive tools。

## 8. Canary

新routing/agent版本逐步：

```text
internal
→ 5%
→ 25%
→ 50%
→ 100%
```

按feature flag/organization cohort；每阶段观察质量/错误/成本。

## 9. Auto Rollback

触发：

- error spike；
- constraint regression；
- cost异常；
- provider fail；
- quality primary metric显著下降。

切换production alias回旧版本；正在运行的Run保持其exact frozen version，按兼容策略完成。

## 10. Human Evaluation

设计质量关键suite：blind A/B pairwise，不显示model/version品牌。记录reviewer、随机顺序、tie、comments。

## 11. Online Feedback

用户select/reject/edit depth作为辅助signal，不能简单等同质量（受任务/用户偏好影响）。与离线benchmark共同看。

## 12. LangSmith

使用Experiment/Dataset/Trace支持LLM/Agent评测；LUMI release manifest、最终gate decision、成本/视觉自有指标仍保存在repo/DB。

## 13. Release Report

```text
candidate manifest
baseline manifest
offline suites
human eval
shadow metrics
canary metrics
cost delta
latency delta
known regressions
approval
```

保存到 `reports/ai-releases/`。

## 14. Tests

- badcandidate被block；
- cost regression；
- security single failure；
- production alias rollback；
- running old version不热变；
- shadow no side effects；
- canary cohort stable。

## 15. 验收标准

- [ ] Production baseline可重现。
- [ ] Candidate manifest完整。
- [ ] Critical guardrails 0 failure。
- [ ] Shadow/Canary机制存在。
- [ ] rollback无需重新部署所有代码即可完成可配置版本切换（适用时）。
- [ ] Release report存档。

## 16. Definition of Done

```text
AI release gate automated
+ bad-candidate drills block correctly
+ canary/rollback tested
```

下一节点：NODE-71 Staging Acceptance。

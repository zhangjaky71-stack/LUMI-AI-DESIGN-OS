# NODE-70 — AI Regression, Experiment & Release Gate

> Phase: 9 Production Readiness  
> Status: **SOURCE IMPLEMENTED / RELEASE BLOCKED**  
> Priority: P0 / AI RELEASE BLOCKER  
> Depends on: NODE-05, NODE-23, NODE-30～32, NODE-46～51, NODE-67  
> Produces: Production Baseline、Candidate比较、Shadow/Canary、Agent/Prompt/Model/Skill/Recipe发布门禁

---

## 1. 目标

模型、Prompt、Agent、Skill和Recipe每次更新都可能“看起来更聪明但实际某类任务变差”。建立统一AI release process，任何生产别名切换必须有Benchmark证据。

NODE-70 source baseline 已实现；当前仍缺真实 production baseline、真实 candidate 评测、人评、shadow/canary 与 Staging rollback 证据，因此不能标记 COMPLETE。

## 2. Versioned Candidates

Release unit必须冻结：

```text
git SHA
agent version
system prompt/template hash
skill versions
recipe version
model routing policy
critic version
constraint policy
context policy
eval suite versions
benchmark response profile
```

实现：`evals/release.py::ReleaseManifest`。

Floating identity（`latest/main/dev/unknown/*`）被拒绝；manifest生成确定性fingerprint。

## 3. Baseline

Production运行版本形成immutable baseline manifest。每次评测：

```text
candidate vs exact production baseline
```

不是跟“上次我电脑上跑的结果”比。

`mode=release` 会拒绝fixture baseline/candidate evidence。

## 4. Blocking Eval Suites

当前可由既有NODE-05 harness直接执行的blocking suites：

```text
smoke
auto-repair
visual-critic
```

`product-parity`和`model-provider`当前属于规格/benchmark定义，不冒充已执行Suite，而作为production supplemental evidence要求。

Critical per-case metrics为零容忍（存在于对应suite时）：

```text
critical_safety_failures
constraint_violation_count
unsafe_branch_overwrite
paid_without_reservation
loop_bound_exceeded
```

单个critical case失败，即使aggregate看起来仍正常，也直接BLOCK。

## 5. Statistical Rules

真实随机模型/人评报告至少包含：

```text
sample size
mean/success rate
delta
confidence method
confidence interval where applicable
```

`evals/statistics.py`提供sample summary与Wilson 95% interval。系统不会因为小样本正向delta自动宣称显著提升。

Policy要求provider benchmark、人评、shadow、canary至少达到minimum statistical sample size并声明confidence method。

## 6. Guardrails

绝不允许回归：

```text
critical security/safety
cross-tenant/tool permission
duplicate paid side effect
hard constraint golden suite
schema validity
unsafe repair overwrite
unbounded repair loop
```

质量、成本、延迟、错误率均是release维度。

## 7. Shadow

实现：`evals/release_control.py::validate_shadow_plan`。

Shadow只允许：

- 授权/脱敏输入；
- candidate结果不展示；
- external side effects关闭；
- destructive tools关闭；
- 明确付费预算。

## 8. Canary

固定阶段：

```text
internal
→ 5%
→ 25%
→ 50%
→ 100%
```

实现：`RolloutState`、`advance_canary`、`canary_action`。

自动ROLLBACK条件：

- provider failure；
- critical failure；
- offline gate不再green；
- error ratio > 1.2x；
- cost ratio > 1.2x；
- quality delta < -0.02。

## 9. Rollback

`rollback()`把production alias恢复为exact baseline version。

Source contract已实现；真实路由/配置层的alias切换必须在Staging证明无需全服务重部署（架构适用时），并证明已运行Agent Run继续使用其frozen exact version。

## 10. Human Evaluation

生产发布的视觉质量必须有blind A/B pairwise：

- 隐藏model/version品牌；
- 随机顺序；
- reviewer/audit reference；
- A/B/tie；
- sample size + confidence method。

用户select/reject/edit depth仅为辅助signal。

## 11. Live Provider Boundary

PR不自动花费真实provider预算。

手动live preflight要求：

```text
LUMI_LIVE_EVAL_ENABLED=1
API key
positive budget
exact suite ACK
SIDE_EFFECT_MODE=none
budget <= configured maximum
```

当前live workflow只做授权preflight，不把READY当作provider benchmark结果。

## 12. Release Policy

权威policy：`evals/release/policy-v1.json`。

除三套blocking executable suites外，production release还要求：

```text
product_parity_acceptance
model_provider_benchmark
security_agent_red_team
human_pairwise_visual
shadow
canary
rollback_drill
```

全部必须PASS并带evidence reference。

## 13. Release Report

正式decision由：

```text
scripts/ai-release-gate.py
```

生成并归档至：

```text
reports/ai-releases/
```

失败decision也保留，不覆盖历史证据。

## 14. CI

`.github/workflows/ai-regression-release-gate.yml`：

- `source-contract`：dependency-free release contract；
- `canonical-eval-tests`：`uv sync --frozen` + benchmark/release tests；
- `live-provider-preflight`：仅workflow_dispatch；
- aggregate release gate要求source与canonical都成功。

NODE-66遗留root `uv.lock` freshness blocker未被绕过。

## 15. Tests / Drills

已加入source/test contract：

- clean fixture candidate passes contract mode；
- floating candidate identity被拒绝；
- single critical case被block；
- fixture evidence不能通过production release mode；
- shadow side effect被拒绝；
- canary progression；
- quality/provider failure触发rollback action；
- rollback恢复baseline alias；
- statistical helper uncertainty记录；
- live eval默认SKIPPED。

## 16. 验收标准

- [ ] Production baseline可重现（真实环境证据待补）。
- [x] Candidate manifest contract完整。
- [x] Critical guardrails在source contract中为0 failure原则。
- [x] Shadow/Canary机制source contract存在。
- [ ] rollback真实alias integration在Staging验证。
- [x] Release report archive/CLI contract存在。
- [ ] Production release report真实存档并通过。

## 17. Definition of Done

```text
AI release gate automated
+ bad-candidate drills block correctly
+ real production baseline captured
+ human/provider/security supplemental evidence green
+ shadow/canary runtime evidence green
+ real alias rollback tested
+ canonical repository gates green
```

当前状态：**SOURCE IMPLEMENTED / RELEASE BLOCKED**。

详细流程：`docs/ai-release/NODE-70-AI-RELEASE-PROCESS.md`  
Release Evidence：`docs/release-evidence/NODE-70-AI-REGRESSION-RELEASE-EVIDENCE.md`

下一节点：NODE-71 Staging Acceptance。

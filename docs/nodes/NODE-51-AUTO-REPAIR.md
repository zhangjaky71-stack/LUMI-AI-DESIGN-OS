# NODE-51 — Auto Repair Loop

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 CORE QUALITY  
> Depends on: NODE-47, NODE-50, NODE-32, NODE-27  
> Produces: Critic→RepairPlan→执行→再评估的有界闭环、回退/预算控制

---

## 1. 目标

让系统能对可修复缺陷自动改进，但绝不进入无限“Agent觉得还可以更好”的循环。Repair必须受规则、预算、最大迭代数和质量回退保护。

## 2. Input

```text
failed artifact/design version
QualityResult
constraints
remaining budget
repair history
```

## 3. RepairPlanner

将 violations映射：

```text
STRUCTURAL_DESIGN_OP
LOCAL_IMAGE_EDIT
REGENERATE_ELEMENT
REGENERATE_ARTIFACT
COPY/TYPOGRAPHY_FIX
MANUAL_REVIEW
```

优先最小、便宜、可逆的修复。

## 4. Rules

例如：

```text
headline overflow → structural text/layout
wrong QR → restore original QR asset/geometry
background defect → local image edit
product identity fail → protected compositing/new generation with stronger refs
```

不能用“重新生成整张”作为所有问题默认解法。

## 5. Loop Bound

每 QualityProfile：

```text
max_auto_repair_iterations = 2 or 3
max_repair_cost
minimum_expected_gain
```

达到限制：REVIEW_REQUIRED/FAIL，不继续烧钱。

## 6. Quality Comparison

修复后：

```text
new score
vs source score
```

如果 hard violations新增，立即reject new candidate。若总质量显著下降，branch head不切换，并保存内部repair failure record。

## 7. Constraint Safety

任何 RepairPlan先NODE-39 preflight；生成式结果postflight。Critic的repair建议不能绕hard constraints。

## 8. Versioning

每次成功/候选repair创建新 ArtifactVersion，并 lineage `EDITED_FROM/REPAIRED_FROM` metadata；批准的是最终exact version。

## 9. Budget

RepairPlanner获得 remaining budget。付费repair前reserve；预算不足：

- 尝试免费/结构化修复；
- 或请求用户增加预算；
- 不产生隐性负余额。

## 10. Deterministic Repairs

P0建立高价值确定性修复器：

```text
text overflow shrink/reflow
safe-area move
alignment
locked asset restore
QR restore
resolution upscale route
```

这些通常比重新调用大模型稳定。

## 11. Agentic Repairs

复杂composition/style问题可用Repair Agent，但输出structured ops/spec；权限与普通Agent一致受Tool Gateway限制。

## 12. Learning Signal

记录：violation、repair action、before/after score、human accept/reject。可作为未来Data Flywheel数据，但不自动用于训练，需数据治理。

## 13. Tests

- deterministic repair；
- max loop；
- budget exhausted；
- quality worsened rollback；
- new hard violation；
- version lineage；
- concurrent user edit causes stale conflict。

## 14. Acceptance Scenario

```text
生成海报
→ Critic发现标题溢出+背景视觉噪声
→ 结构化缩小/重排标题
→ local edit背景
→ re-eval
→ score提升且产品/Logo/QR不变
→ READY
```

## 15. 验收标准

- [ ] Repair Loop严格有界。
- [ ] 最小修改优先。
- [ ] worse candidate不覆盖好版本。
- [ ] budget/constraints始终生效。
- [ ] before/after质量可解释。
- [ ] stale user edit不会被repair覆盖。

## 16. Definition of Done

```text
auto repair orchestrator implemented
+ bounded-loop tests green
+ golden repair eval improves baseline
```

完成 Phase 6，下一节点：NODE-52 App Shell。

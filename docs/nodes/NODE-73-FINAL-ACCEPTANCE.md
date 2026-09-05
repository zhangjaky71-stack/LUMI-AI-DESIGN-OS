# NODE-73 — Final Product Acceptance

> Phase: 9 Production Readiness  
> Status: **SOURCE GATE IMPLEMENTED / FINAL PRODUCT NOT ACCEPTED / RUNTIME EVIDENCE PENDING**  
> Priority: P0 / PROJECT COMPLETION  
> Depends on: NODE-00～72  
> Produces: 最终验收矩阵、证据包、产品级结论、剩余Gap/运营移交

---

## 0. Implementation Status — 2026-08-15

NODE-73 的**最终验收控制面源码已经实现**，但 LUMI 当前不能标记为 Product Accepted。

当前合法结论：

# NOT ACCEPTED — SEE BLOCKING GAPS

只有真实 Release Package 通过 `scripts/final-acceptance-gate.py` 并返回：

```text
accepted=true
passed=true
blockers=[]
```

时，才允许输出：

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

### 已实现的 Final Gate source baseline

- `final/acceptance/manifest-v1.json`：冻结 46 条 Final Acceptance scenarios；
- 六个必需上游 gate：Security / Recovery / Performance / AI Regression / Staging Acceptance / Production Deployment；
- P0 必须 PASS；P0 `BLOCKED_EXTERNAL`/`DEFERRED_NON_CRITICAL` 均 NO-GO；
- Critical/High 不允许通过 defer/block 变绿；
- 非关键 defer 必须包含 owner/reason/impact/target release/workaround；
- `release-manifest.json` 冻结 exact RC、Production deployment、所有 upstream decisions 与 acceptance evidence 的 path + SHA-256；
- upstream decision 必须 `decision_id + passed=true + frozen evidence_refs`；
- Performance / AI / Staging / Production gate 必须与 final RC SHA/version/migration head 完全一致；
- 每个 PASS scenario 必须有至少一个 frozen evidence ref；
- Final Gate 会重新计算所有 evidence SHA-256，拒绝替换/篡改；
- acceptance evidence scenario set 必须与 canonical matrix 完全相同，不能删掉失败项；
- Product / Engineering / Security / Operations / Release Owner 全部必须 APPROVED；
- operational handoff 八类 owner 全部必须填写；
- dependency-free negative drill 覆盖 P0 fail/block、缺 evidence、upstream false/hash/RC swap、Production RC swap、open blocker、缺审批等；
- `NOT_RUN` skeleton generator 保证未执行项无法意外 PASS；
- `Final Product Acceptance Gate` workflow 已建立，且继续保留 canonical `uv sync --frozen` gate，不绕过既有依赖锁问题。

### 当前阻断最终接受的事实

- NODE-68/69/70/71/72 的 Production-like/runtime/cloud evidence 尚未全部 PASS；
- NODE-71 尚无真实 Production-like Staging `passed=true` exact RC；
- NODE-72 明确仍为 GO-LIVE BLOCKED，Production 尚未由真实 evidence 证明上线；
- 六个目标 production runtime transport/entrypoint/image promotion chain 尚未全部证明；
- platform-wide daily provider-dollar hard stop 尚未证明为 durable runtime enforcement；
- Production Sandbox egress isolation 尚未完成最终验证；
- root canonical dependency lock freshness blocker 尚未解决；
- 最近 readiness-node GitHub Actions 仍受到 account Billing/spending-limit 导致的 runner-start blocker；
- NODE-73 尚未形成任何真实 Production release 的完整 final evidence package。

因此，本文件中的 P0 验收条件不能因为 Final Gate 源码存在而勾选。

详细 source/evidence 状态：

```text
docs/release-evidence/NODE-73-FINAL-ACCEPTANCE-RELEASE-EVIDENCE.md
docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md
reports/final-acceptance/README.md
```

## 1. 目标

判断 LUMI 是否真正达到本项目最初标准：从底层架构、前后端、Agent、设计编辑、生成、数据、安全、成本、部署到真实交付，形成类似Lovart类AI Design Agent的产品级系统，而不是Demo。

只有全部关键门禁通过才标：

```text
LUMI AI DESIGN OS — PRODUCT ACCEPTED
```

否则输出明确Gap，不用“基本完成”掩盖失败。

## 2. Acceptance Dimensions

```text
Architecture
Engineering
Security
Reliability
Agent Intelligence
Design Intelligence
Canvas/Edit UX
Generation
Brand
Quality
Version/Provenance
Collaboration
Billing/SaaS
Observability
Performance
Recovery
Production Operations
```

Canonical machine matrix 已冻结在：

```text
final/acceptance/manifest-v1.json
```

## 3. Architecture Acceptance

证明：

- LangGraph控制生命周期；
- Deep Agents受控自治；
- Gateway隔离Provider/Tools；
- Design IR独立renderer；
- Constraint server enforcement；
- Artifact不可变versions；
- Business DB与Agent checkpoint分离；
- Sandbox安全执行。

架构违规必须有ADR。

## 4. Core User Journey A — Zero-to-Brand

用户只提供自然语言：

> 为一家精品咖啡品牌做完整设计，包括研究、品牌定位、视觉方向、Logo、品牌规范、包装、菜单、海报、社媒和短视频。

验收：

```text
Create Project
→ Brief Agent
→ Research + sources
→ Brand Strategy
→ Creative Directions
→ Human Approval
→ Moodboard
→ Brand Kit
→ Design/Generation
→ Canvas editable assets
→ Critic/Brand/Identity QA
→ Repair
→ Multi-format Export
```

必须可暂停/恢复，有Timeline、成本和versions。

## 5. Core User Journey B — Precision Local Edit

选择第二张海报：

> 产品和Logo都不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

必须证明：

```text
selected exact version
→ intent/constraints
→ title structural edit -15%
→ background structural/local edit
→ product identity unchanged
→ logo unchanged
→ QR geometry/payload/scannability unchanged
→ visual quality pass
→ new version
→ old version remains restorable
```

这是LUMI从“生图聊天机器人”升级为“设计Agent”的核心验收。

## 6. Core User Journey C — Multi-size Campaign

从approved主视觉生成：

```text
1:1
4:5
9:16
16:9/banner
```

不能简单拉伸；需要布局适配时创建独立DesignVersions，并保持Brand/Product约束。

## 7. Core User Journey D — Failure Recovery

生成过程中强制：

- Agent worker restart；
- provider timeout；
- duplicate request；
- SSE disconnect。

最终run可恢复或明确失败，且：

```text
no duplicate paid generation
no corrupt artifact
no lost approved version
```

## 8. Security Acceptance

Release blockers：

- cross-tenant leak = 0；
- Critical/High unresolved = 0 launch default；
- sandbox escape = 0；
- secret exposure = 0；
- prompt injection不能越权Tool；
- SSRF metadata/internal blocked；
- payment/credit replay blocked。

## 9. Reliability Acceptance

- backup restore实际完成；
- Run resume；
- provider fallback；
- queue redelivery idempotent；
- SLO dashboard/alerts；
- bad deploy rollback。

## 10. Quality Acceptance

Benchmark Harness against frozen baseline：

- hard constraint suite 100% target for deterministic cases；
- golden precision edit critical cases全部PASS；
- visual/brand/identity达到NODE-70 release threshold；
- no critical regression；
- human pairwise结果达到候选release规则。

## 11. Cost Acceptance

随机抽取真实 runs核对：

```text
Provider request
↔ Generation
↔ Operation
↔ Cost Ledger
↔ AgentRun/Task
↔ Billing usage if enabled
```

误差/estimated项有confidence和reconciliation，不存在无法解释的大额“other”。

并且 first-day/provider budget 中记录的限制必须在 durable runtime enforcement point 被证明，而不是只存在于 manifest 文本。

## 12. Data / Provenance Acceptance

任一final Artifact能查：

```text
source assets
parent versions
model/provider
agent/recipe/skills
prompt/template hash
constraints
brand rules
quality result
creator/time
git/runtime version
rights metadata
```

## 13. Frontend Acceptance

桌面核心：

- Projects；
- AI Workspace；
- Infinite Canvas；
- Layers/Inspector；
- Agent Timeline；
- Brand Kit；
- Versions/Compare；
- Export；
- Approval；
- Billing/Team按release scope。

无核心dead-end/placeholder伪功能。

## 14. Performance Acceptance

NODE-69 launch profile全部达到冻结阈值；Canvas普通场景流畅；API、SSE、queue、DB没有已知P0容量阻断。

## 15. Production Acceptance

- real HTTPS/domain；
- Production DB/storage/broker；
- backups；
- secrets；
- observability；
- canary；
- incident runbooks；
- support/admin；
- quotas/cost caps。

如果外部商业provider账号尚未开通，对应真实能力不能算最终Production PASS。

## 16. Documentation Acceptance

必须存在：

```text
Architecture
NODE specs
ADRs
API/OpenAPI
Event schemas
Design IR/Constraint schemas
DB ERD/migrations
Runbooks
Security threat model
Benchmark reports
Staging acceptance
Production deploy
Operator guide
User/admin basics
```

## 17. Evidence Package

`reports/final-acceptance/<release>/`：

```text
release-manifest.json
acceptance-evidence.json
final-decision.json
acceptance-matrix.md
benchmark-summary.json
security-summary.md
performance-summary.md
recovery-summary.md
cost-reconciliation.md
browser-e2e.md
known-gaps.md
upstream/
```

所有机器决策/关键证据引用都冻结 path + SHA-256，不允许依赖 mutable `latest`。

## 18. Status Rules

每条：

```text
PASS
FAIL
BLOCKED_EXTERNAL
DEFERRED_NON_CRITICAL
```

P0 必须 PASS。P0 FAIL、P0 BLOCKED_EXTERNAL 或 P0 DEFERRED_NON_CRITICAL 均不得 PRODUCT ACCEPTED。

Critical/High 不能通过 defer/block 变绿。

## 19. Gap Policy

非关键P1/P2可以defer，但必须：

```text
owner
reason
impact
target release
workaround
```

不能删除验收项让报告变绿；Final Gate 要求 acceptance evidence 的 scenario ID 集合与 canonical matrix 完全一致。

## 20. Operational Handoff

验收后建立持续节奏：

- weekly provider/cost/quality review；
- monthly security/dependency；
- quarterly DR drill；
- AI release gate for every production AI change；
- capacity planning；
- customer feedback → governed data flywheel。

Final release manifest 还必须冻结：

```text
on-call owner
support owner
incident commander rotation
first-day watch owner
quality/cost review owner
security/dependency review owner
DR drill owner
capacity review owner
```

## 21. 最终签署条件

只有同时满足：

```text
P0 product matrix PASS
+ security gate PASS
+ recovery PASS
+ performance PASS
+ AI regression PASS
+ staging acceptance PASS
+ production deployment PASS
+ no unresolved release blocker
+ final approvals APPROVED
+ operational handoff complete
```

才写：

# LUMI AI DESIGN OS — PRODUCT ACCEPTED

否则：

# NOT ACCEPTED — SEE BLOCKING GAPS

当前项目状态属于后者。

## 22. Definition of Done

```text
final evidence package complete
+ all P0 acceptance gates passed
+ production release manifest frozen
+ operational handoff complete
+ final machine decision accepted=true
```

当前：**NOT DONE / FINAL PRODUCT NOT ACCEPTED**。

NODE-73真正完成后，本轮Architecture V2产品级工程主路线才算验收完成；在此之前仍需关闭真实 runtime / Staging / Production / Security / Recovery / Performance / AI / Cost 等 P0 gap。

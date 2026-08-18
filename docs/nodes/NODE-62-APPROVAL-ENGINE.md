# NODE-62 — Approval & Review Workflow

> Phase: 8 SaaS & Collaboration  
> Status: CORE IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0/P1 CORE WORKFLOW  
> Depends on: NODE-28, NODE-42, NODE-57, NODE-61  
> Produces: durable Approval Domain、exact-version review、immutable decision/audit、retryable effects、Formal Approval Workspace UI、LangGraph bridge contracts

---

## 1. 目标

把 Human-in-the-loop 从一个技术 interrupt 变成产品级审批流程。用户能批准创意方向、ArtifactVersion、预算升级或高风险外部动作，并确保批准的是 exact version，而不是后来变化的内容。

本节点当前已经完成 **ArtifactVersion Approval 的 durable core**，并把旧的“UI 直接 resume Graph”审批旁路封堵；但 production orchestration/worker/restart E2E 尚未闭合，所以状态保持 **NOT COMPLETE**。

## 2. Approval Domain

Canonical 类型：

```text
CREATIVE_DIRECTION
ARTIFACT_VERSION
BRAND_RULE_SET
BUDGET_INCREASE
EXTERNAL_PUBLISH
DESTRUCTIVE_ACTION
CUSTOM_REVIEW
```

Canonical 状态：

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
EXPIRED
CANCELLED
SUPERSEDED
```

P0 当前产品入口只开放 `ARTIFACT_VERSION`；其余类型保留在 Domain/schema 中，必须等各自 subject resolver / permission / side-effect contract 落地后再开放 UI。

## 3. Durable 数据模型

Migration：

```text
20260818_0021 → 20260818_0022
```

新增四层持久资源：

```text
approval_requests       # 业务审批真相
approval_decisions      # 不可变用户决策
approval_audit_events   # 不可变审计轨迹
approval_effects        # 可重试副作用
```

核心原则：

```text
Approval decision truth != Artifact / LangGraph side-effect execution
```

用户决定先 durable commit；Artifact 状态切换与 Graph resume 通过 `approval_effects` 单独投递。这样 runtime crash 不会抹掉已经发生的人类决策。

## 4. Exact Subject / Snapshot

Artifact approval强制绑定：

```text
subject_type = ARTIFACT_VERSION
subject_id = artifact_version_id
artifact_version_id = exact UUID
subject_version_ref = artifact:vN
subject_snapshot_hash = ArtifactVersion.content_hash
```

创建审批时要求 exact version 当前为 `READY`。

提交 decision 时再次锁定并校验：

- exact ArtifactVersion仍存在；
- `content_hash` 与 request snapshot 一致；
- exact version本身仍为 `READY`；
- Approval仍为 `PENDING`；
- actor仍有权限；
- 未过期。

**不会检查 branch head/latest version。** 因此 v4 出现不会让 v3 approval漂移或自动失效；批准 v3 永远只批准 v3。

如果 exact subject被旧旁路改变或 snapshot不一致，Approval durable transition为 `SUPERSEDED`，然后客户端收到 stale conflict。

## 5. Permission

复用现有 Auth permission：

```text
artifact.approve
```

Artifact decision必须同时满足：

```text
organization member
AND
(project creator OR explicit project_members member)
AND
actor permissions contains artifact.approve
```

Viewer没有 `artifact.approve`；Owner/Admin/Editor按现有 policy获得该能力。

浏览器从 session permissions 投影控制，但服务端仍是最终授权边界。

## 6. Idempotency

审批请求：

```text
UNIQUE (organization_id, request_operation_id)
```

审批 decision：

```text
UNIQUE (organization_id, operation_id)
UNIQUE (approval_id, actor_id)
```

Effect：

```text
UNIQUE (approval_id, effect_type)
UNIQUE (organization_id, operation_id)
```

所有产品 write要求 UUID `Idempotency-Key`。

## 7. Approval Policies

Schema保留：

```text
ANY_ONE
ALL
MIN_N
ROLE_BASED_SEQUENCE
```

当前 P0执行语义为：

```text
ANY_ONE / policy_version=1 / min_approvals=1
```

多审批人聚合/sequence尚未实现，不能只因为枚举存在就宣称支持。

## 8. Decision / Request Changes

正式 decision：

```text
APPROVED
REJECTED
CHANGES_REQUESTED
```

Reject / Request Changes必须带 reason 或结构化 feedback。

Workspace可提交：

```text
comment
selected Canvas node_ids[]
requested_changes[]
```

这些进入 canonical `approval_decisions.feedback_json`。

`CHANGES_REQUESTED → Repair/Edit task` 的自动 recipe 还未闭合，继续列 P0 gap。

## 9. Expiry / Stale

高风险 Approval可带 timezone-aware `expires_at`。

过期决策不会默认批准，而是：

```text
PENDING → EXPIRED
```

snapshot/state不再满足：

```text
PENDING → SUPERSEDED
```

状态先 durable commit，再返回 stale conflict，保证重试/重启后仍能看到真实结果。

## 10. Immutable Audit / Outbox

Audit记录：

```text
REQUESTED
DECISION_RECORDED
EXPIRED
SUPERSEDED
```

Decision actor、status transition、时间与 exact subject关联都持久化。

Approval Outbox只投影 IDs / decision type 等通知所需字段，不复制用户评论、Prompt、Provider response或私有 Graph state。

Audit API额外要求 `admin.audit.read`。

## 11. Retryable Effects

当前 effect types：

```text
ARTIFACT_VERSION_APPROVE
AGENT_RUN_RESUME
```

状态：

```text
PENDING
RUNNING
COMPLETED
FAILED
CANCELLED
```

`ApprovalEffectProcessor`：

- durable claim；
- attempt counter；
- COMPLETED幂等；
- FAILED可重试；
- Artifact adapter只批准 effect payload锁定的 exact version；
- Agent adapter用 effect operation UUID resume并传 `{approval_id, decision, reason, feedback}`。

当前缺口：生产 worker/composition、RUNNING crash lease/reclaim、dead-letter/escalation 尚未闭合。

## 12. LangGraph Bridge

目标 contract：

```text
Recipe Approval Step
→ create durable Approval
→ Graph interrupt contains approval_id
→ Workspace Formal Approval UI
→ decision API durable commit
→ approval_effects.AGENT_RUN_RESUME
→ resume Graph with approval_id + decision
```

已经实现：

- internal Approval service可保存 `agent_run_id/task_id/interrupt_id/resume_version`；
- public browser create schema不能伪造这些 bridge fields；
- Agent resume adapter contract已实现；
- Workspace旧的 `Approve & continue → resumeAgentRun` 直接旁路已删除。

尚未实现：Recipe/Graph节点自动创建 Approval并把 `approval_id` 写入 interrupt；production effect worker真正消费/恢复 Graph。因此“Graph restart后可resume”尚未通过 E2E。

## 13. Legacy Artifact Approve Hardening

旧：

```text
POST /artifact-versions/{id}/approve
```

不再允许客户端提交 `approved_by_id`。

Compatibility schema会 fail-closed，并抛出：

```text
DIRECT_ARTIFACT_APPROVAL_DISABLED_USE_FORMAL_APPROVAL_ENGINE
```

底层 `ArtifactEngineService.approve_version()` 保留，只能由 Formal Approval effect adapter作为受控副作用调用。

## 14. Product UI

Workspace新增 Formal Approval Panel：

- 对当前 Canvas exact ArtifactVersion请求审批；
- 明确展示 exact version ID/ref；
- 不自动切换 latest；
- PENDING review；
- Approve / Request Changes / Reject；
- reject/changes强制 feedback；
- 可附带当前 Canvas selection nodes；
- exact-version decision history；
- 其他版本的 pending approval只提示，不应用到当前版本；
- 无 `artifact.approve` permission 时只读。

Agent Timeline遇到 technical approval/review interrupt时只显示 governance提示，不再提供 direct resume按钮。

## 15. Safe Product DTO

浏览器 Approval DTO明确排除：

```text
interrupt_id
resume_version
effect payload
raw last_error
prompt / reasoning
provider_request_id
storage_key
```

Effect错误只投影 `has_error: boolean`。

## 16. Tests / Acceptance Evidence

当前 tests覆盖：

- exact subject + snapshot invariant；
- public create不能伪造 Graph bridge；
- legacy direct Artifact approval fail-closed；
- `artifact.approve` permission检查；
- v4出现不影响v3 exact approval；
- request/decision/effect idempotency约束；
- immutable decision/audit/effect分层；
- reject/changes feedback requirement；
- admin audit permission；
- Outbox不复制 feedback/reason；
- Agent resume adapter携带 formal approval id/decision；
- safe browser DTO拒绝 internal fields；
- Workspace不再 direct `resumeAgentRun` 审批。

## 17. 开放 P0

主要开放项：

- production `approval_service_factory` composition；
- Recipe/Graph节点自动创建 Approval + interrupt `approval_id`；
- production approval effect worker；
- RUNNING effect crash lease/reclaim / DLQ；
- real ArtifactEngine/AgentRun effect adapters composition；
- Graph restart + stale interrupt E2E；
- `CHANGES_REQUESTED → Edit/Repair task` recipe；
- multi-approver policy执行；
- 非 Artifact subject resolver / UI；
- approval notification consumer/UX；
- Browser + PostgreSQL + Agent runtime E2E；
- Hosted CI executed green。

以 `reports/nodes/NODE-62/gap-ledger.json` 为准。

## 18. 验收状态

- [x] Approval是正式 durable Domain对象。
- [x] Artifact approval exact version锁定。
- [x] Unauthorized actor被 formal permission fence拒绝。
- [x] Request/decision/effect 幂等 contract建立。
- [x] Reject / Changes Request结构化反馈 durable。
- [x] Expiry/Superseded有明确 durable状态。
- [x] Immutable audit + safe Outbox建立。
- [x] Workspace Formal Approval UI落地。
- [x] Legacy direct UI/Artifact approval路径 fail-closed。
- [ ] Graph node实际创建 Approval并携带 `approval_id` interrupt。
- [ ] production worker执行并恢复 Graph。
- [ ] Graph restart/stale/idempotency E2E green。
- [ ] Request Changes自动进入修订任务。
- [ ] Multi-approver policies执行完成。
- [ ] Hosted CI真实步骤 green。

## 19. Definition of Done

当前状态：

```text
approval durable core + exact-version UI + effect/bridge contracts implemented
BUT
production graph integration + effect worker + restart E2E + Hosted green remain open
```

因此 **NODE-62 NOT COMPLETE**。

下一节点：NODE-63 Billing。

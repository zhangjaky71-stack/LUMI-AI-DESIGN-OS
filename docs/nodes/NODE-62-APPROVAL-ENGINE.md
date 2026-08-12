# NODE-62 — Approval & Review Workflow

> Phase: 8 SaaS & Collaboration  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 CORE WORKFLOW  
> Depends on: NODE-28, NODE-42, NODE-57, NODE-61  
> Produces: Approval Domain、LangGraph interrupt桥接、版本锁定审批、Reject/Changes与审计

---

## 1. 目标

把 Human-in-the-loop 从一个技术 interrupt 变成产品级审批流程。用户能批准创意方向、Logo、ArtifactVersion、预算升级或高风险外部动作，并确保批准的是 exact version，而不是后来已经变化的内容。

## 2. Approval Types

```text
CREATIVE_DIRECTION
ARTIFACT_VERSION
BRAND_RULE_SET
BUDGET_INCREASE
EXTERNAL_PUBLISH
DESTRUCTIVE_ACTION
CUSTOM_REVIEW
```

## 3. Approval Record

```text
id
organization_id
project_id
agent_run_id?
task_id?
type
subject_type
subject_id
subject_version
status
requested_by
required_role/permission
payload_summary
expires_at?
created_at
resolved_at
```

## 4. Status

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
EXPIRED
CANCELLED
SUPERSEDED
```

## 5. Exact Subject

Artifact approval绑定 `artifact_version_id`。若新v4出现，旧v3 approval仍只适用于v3；UI可标旧审批 superseded，但不能把approval漂移到head。

## 6. LangGraph Bridge

```text
Recipe Approval Step
→ create Approval row
→ Graph interrupt with approval_id
→ UI card
→ user decision API
→ transaction validates permission/version/status
→ mark approval
→ Command(resume={approval_id, decision})
```

重复decision idempotent。

## 7. Request Changes

`CHANGES_REQUESTED`包含结构化/文本反馈：

```text
comment
node/region refs
requested changes
```

Recipe将其转为Repair/Edit tasks，而不是直接Approve后继续。

## 8. Multi-approver

P1支持：

```text
ANY_ONE
ALL
MIN_N
ROLE_BASED_SEQUENCE
```

P0单一授权审批者即可，但schema预留policy version。

## 9. Stale Protection

审批提交时检查：

- subject仍存在；
- version匹配；
- approval未resolved；
- actor仍有permission；
- run状态允许resume。

否则 `APPROVAL_STALE`。

## 10. Expiry

高风险审批可过期；过期后Graph进入明确状态或重新请求，不默认approve。

## 11. Notifications

Approval required产生站内通知；P1 email。提醒频率可配置，避免骚扰。

## 12. Audit

不可变记录：requested/resolved/superseded，以及decision actor/reason/version。普通日志不可替代。

## 13. Tests

- approve exact version；
- stale v3 vs v4；
- unauthorized viewer；
- duplicate approve；
- request changes→task；
- expiry；
- Graph restart while waiting；
- multi approver policy P1 fixture。

## 14. 验收标准

- [ ] Approval是正式Domain对象。
- [ ] exact version锁定。
- [ ] LangGraph restart后仍可resume。
- [ ] stale/unauthorized被拒绝。
- [ ] Request Changes可重新进入工作流。
- [ ] 全过程Audit。

## 15. Definition of Done

```text
approval service/UI/graph bridge implemented
+ stale/restart/idempotency E2E green
```

下一节点：NODE-63 Billing。

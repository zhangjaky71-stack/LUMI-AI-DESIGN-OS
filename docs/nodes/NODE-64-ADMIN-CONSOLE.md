# NODE-64 — Admin & Operations Console

> Phase: 8 SaaS & Collaboration  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P1 / OPERATIONS  
> Depends on: NODE-16, NODE-19, NODE-22～27, NODE-30～33, NODE-42, NODE-63  
> Produces: 内部Admin UI、Run/Provider/Cost/DLQ/Registry/Feature Flags运维入口

---

## 1. 目标

生产系统必须可运营。Admin不是给普通客户的“设置页”，而是内部高权限控制面，用来处理失败任务、成本、Provider状态、Agent版本、DLQ、用户/组织支持与安全事件。

## 2. 独立权限

Admin角色：

```text
SUPPORT_READ
OPS
BILLING_ADMIN
AI_CONFIG_ADMIN
SECURITY_ADMIN
SUPER_ADMIN (极少)
```

不能因为Organization OWNER就获得平台Admin。

## 3. Core Pages

```text
Dashboard
Organizations
Users
Projects
Agent Runs
Tasks
Artifacts
Providers / Model Registry
Agent Registry
Skill Registry
Recipes
Costs / Usage
Queues / DLQ
Feature Flags
Billing
Audit
Incidents
```

## 4. Dashboard

显示聚合：

- active/failing runs；
- provider health；
- queue depth；
- cost spike；
- quality regression；
- billing/webhook backlog；
- critical alerts。

## 5. Run Inspector

可查看：

```text
run/task state
safe trace links
agent/recipe/model versions
artifacts
errors/retries/fallbacks
budget/cost
approval state
```

普通支持人员不默认看完整用户prompt/私人资产内容。

## 6. DLQ

显示failure summary，可执行：

```text
retry/replay
mark resolved
discard with reason
```

每个动作必须权限+Audit；replay仍经inbox/idempotency。

## 7. Provider Controls

- enable/disable；
- circuit状态；
- routing weight/policy version；
- synthetic health；
-price snapshot查看。

所有变更versioned/audited，危险变更可要求二人审批P2。

## 8. Registry Controls

Agent/Skill/Recipe production alias切换只能选择已通过release gate版本。Admin不能在UI直接编辑任意Python/执行代码。

## 9. User Support

可：

- 查组织/项目metadata；
- revoke session；
- resend invite；
- resolve billing状态。

“Impersonation”若未来实现必须显著banner、短TTL、理由、用户/合规策略和完整audit；P1默认不实现。

## 10. PII / Content Access

采用 break-glass：敏感内容查看需要更高permission、理由、Audit。列表页默认只展示metadata和preview是否存在，不全量展示私人设计。

## 11. Feature Flags

server-side flags：

```text
name
scope global/org/user
value
owner
expiry
reason
created_by
```

安全强制策略不能作为普通feature flag关闭。

## 12. Operational Actions

所有mutation提供dry-run（能做到时）、确认和result。禁止“一个红按钮无说明直接删除全部”。

## 13. Tests

- platform admin vs org owner；
- permission matrix；
- DLQ replay；
- provider disable；
- registry alias only gated version；
- break-glass audit；
- feature flag expiry；
- no secret response。

## 14. 验收标准

- [ ] 运维可定位失败Run/Task。
- [ ] Provider/Queue/Cost可观察。
- [ ] DLQ安全replay。
- [ ] Registry promotion受gate限制。
- [ ] 敏感内容访问最小化并Audit。
- [ ] Org OWNER无平台Admin权。

## 15. Definition of Done

```text
admin console operational flows green
+ RBAC/break-glass tests green
```

下一节点：NODE-65 Audit & Governance。

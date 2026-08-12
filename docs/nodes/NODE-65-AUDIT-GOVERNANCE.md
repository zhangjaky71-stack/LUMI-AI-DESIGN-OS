# NODE-65 — Audit, Governance & Data Retention

> Phase: 8 SaaS & Collaboration  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 SECURITY & ENTERPRISE  
> Depends on: NODE-10, NODE-16, NODE-25, NODE-42, NODE-62, NODE-64  
> Produces: Append-only Audit、Retention、数据删除/Legal Hold接口、审计导出与治理规则

---

## 1. 目标

记录“谁在什么时候对什么做了什么”，用于安全、企业治理、争议和运营排查。Audit与普通应用日志不同：可查询、权限受限、append-only、retention明确。

## 2. Audit Event

```text
id
organization_id?
actor_type
actor_id
session/api_token/agent_run ref
action
resource_type
resource_id
resource_version?
result SUCCESS/DENIED/FAILED
reason_code
request_id/trace_id
ip/security metadata
safe_change_summary
occurred_at
```

## 3. 必审动作

```text
auth/login/session/token
membership/role
project delete/archive
asset delete/download-sensitive
brand rules publish
artifact approval/restore
constraint override
external write tool
billing/credits
admin actions
provider/registry config
DLQ replay
secret/config access events where supported
```

## 4. Change Summary

不默认存完整before/after大型文档。保存：

```text
changed fields
version refs
semantic diff ref
```

敏感内容可放受限evidence store。

## 5. Append-only

应用API不提供普通 UPDATE/DELETE Audit row。数据库角色限制；纠错写新annotation/correction event。

P1可添加tamper-evident hash chain/外部WORM归档作为enterprise profile。

## 6. Retention Classes

```text
SECURITY_AUDIT
BILLING
CONTENT
AGENT_TRACE
TEMP_SANDBOX
EXPORT
ANALYTICS
```

每类有retention policy version。不要“一刀切永久保存所有内容”。

## 7. User Deletion / Privacy

建立Data Subject/Account Deletion workflow接口：

```text
identify scope
→ legal/billing hold check
→ deactivate
→ delete/anonymize eligible data
→ object GC
→ search/vector removal
→ completion record
```

具体法定要求在上线国家/地区前由法律专业人员核验；技术上必须支持执行。

## 8. Legal Hold

Enterprise/legal需要时，hold阻止受影响Artifact/Asset/Audit被GC；创建/解除hold都需高权限和Audit。

## 9. Audit Search

按：

```text
time
actor
action
resource
result
organization
trace
```

cursor pagination。普通Org Admin只能看其组织允许的audit subset；平台security权限更高。

## 10. Export

企业可导出JSON/CSV；大量导出异步job + signed URL + audit。导出本身也是敏感动作。

## 11. Redaction

禁止Audit记录：

```text
password
raw API key
session secret
payment card
full Authorization header
full presigned URL query
```

Prompt/用户内容默认仅hash/ref，不全量进入Audit。

## 12. Agent Audit

Agent actor记录：

```text
agent id/version
run/task
human initiator
Tool write operations
constraint overrides (若允许)
```

Agent不能以“system”模糊身份写外部世界。

## 13. Tests

- append-only；
- permission；
- redaction；
- agent actor；
- admin action；
- retention candidate；
- legal hold blocks GC；
- deletion propagates search/object refs。

## 14. 验收标准

- [ ] 高风险动作都有Audit。
- [ ] Audit不能普通修改/删除。
- [ ] 不保存secrets。
- [ ] retention classes明确。
- [ ] deletion/hold技术路径存在。
- [ ] audit export受权限保护。

## 15. Definition of Done

```text
audit pipeline + governance services implemented
+ redaction/retention/hold tests green
```

完成 Phase 8，下一节点：NODE-66 Security Hardening。

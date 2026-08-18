# NODE-65 — Audit, Governance & Data Retention

> Phase: 8 SaaS & Collaboration  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0/P1 SECURITY & ENTERPRISE  
> Depends on: NODE-10, NODE-16, NODE-25, NODE-42, NODE-62, NODE-64  
> Produces: Append-only Audit、Retention、数据删除/Legal Hold接口、审计导出与治理规则
>
> Acceptance source of truth: `reports/nodes/NODE-65/gap-ledger.json`  
> Implementation evidence: `reports/nodes/NODE-65/implementation.md`

---

## 1. 目标

记录“谁在什么时候对什么做了什么”，用于安全、企业治理、争议和运营排查。Audit与普通应用日志不同：可查询、权限受限、append-only、retention明确。

当前 NODE-65 已实现治理核心契约与数据库边界，但**仍存在生产组合、全系统 Audit ingress、Deletion/Export/Retention worker、统一平台审计查询和 Hosted E2E 等 P0 gap，因此不得标记 COMPLETE**。

## 2. Audit Event

```text
id
organization_id
actor_type
actor_id
session/api_token/agent_run/task ref
action
resource_type
resource_id
resource_version?
result SUCCESS/DENIED/FAILED
reason_code
request_id/trace_id
security metadata
safe_change_summary
retention_class/policy_version
previous_hash/event_hash
occurred_at
```

实现状态：

- 复用既有 `audit_events` 作为组织级 canonical Audit，而不是新建第三套互不兼容日志；
- legacy actor/hash 在收紧约束前先保留原值并规范化；
- 数据库 trigger 拒绝普通 UPDATE/DELETE；
- 新写入维护 organization-scoped `previous_hash -> event_hash` SHA-256 chain；
- organization-scoped PostgreSQL advisory transaction lock 防止并发写入分叉 hash-chain head；
- 默认查询只返回安全摘要，不返回 raw details/security metadata。

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

**当前状态：P0 OPEN。** NODE-65 已定义 canonical Audit sink/contract，但上述所有生产者尚未全部接入。不得以“有 Audit API”替代“高风险动作全部有真实 Audit 证据”。详见 `NODE65-GAP-302`。

## 4. Change Summary

不默认存完整before/after大型文档。保存：

```text
changed fields
version refs
semantic diff ref
```

敏感内容可放受限evidence store。Prompt/用户内容默认仅 hash/ref，不全量进入 Audit。

## 5. Append-only

应用API不提供普通 UPDATE/DELETE Audit row。数据库 `trg_audit_events_immutable` 在 UPDATE/DELETE 前直接拒绝；纠错必须追加新的 annotation/correction event，而不是重写历史事实。

新 canonical 写入同时维护 tamper-evident hash chain；外部 WORM 归档仍属于后续 enterprise hardening，不在本节点冒充完成。

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

每类有版本化 retention policy。Migration 提供的默认天数只是 **technical baseline**，明确要求上线国家/地区前进行法律/隐私专业复核；它们不是法定义务声明。

生产 Retention sweeper + physical GC 仍为 `NODE65-GAP-305`。

## 7. User Deletion / Privacy

技术状态机：

```text
identify scope
→ legal hold check
→ deactivate
→ erase
→ object GC
→ search/vector removal
→ completion record
```

已实现：

- `IDENTIFIED / HOLD_BLOCKED / DEACTIVATED / ERASING / COMPLETED / FAILED` durable 状态；
- `SubjectDeactivationPort`、`ObjectDeletionPort`、`SearchDeletionPort` 三个独立执行端口；
- 任一端口未组合即 fail-closed；
- Object GC 和 Search/Vector GC 都成功后才允许 COMPLETED；
- 执行前重新检查 live Hold；
- 进入 ERASING 的 SQL 再次检查 active Hold；
- Legal Hold 创建和 ERASING transition 共用组织级 advisory xact lock，关闭检查/插入竞争窗口。

未实现为生产完成：durable idempotent deletion worker、crash/retry、完整 data-subject scope discovery/anonymization。详见 `NODE65-GAP-303`、`NODE65-GAP-307`。

具体法定要求在上线国家/地区前由法律专业人员核验。

## 8. Legal Hold

Enterprise/legal需要时，Hold阻止受影响资源被GC；创建/解除Hold都需高权限、reason 和 canonical Audit。

支持 scope：

```text
ORGANIZATION
USER
PROJECT
ASSET
ARTIFACT
AUDIT
```

组织级 Hold 会覆盖组织内资源。普通 Organization ADMIN 只能读取允许的审计，不因 `admin.audit.read` 自动获得 Legal Hold 权限；`governance.manage` 仅由 OWNER 获得。

## 9. Audit Search

支持：

```text
time
actor
action
resource
result
organization
trace
```

使用稳定 cursor pagination。普通 Org Admin 只能查看其组织；平台 SECURITY_ADMIN 跨组织/平台统一查询仍为 P0 `NODE65-GAP-306`。

## 10. Export

核心契约支持 JSON/CSV，`audit.export` 与普通 `admin.audit.read` 分离：

- export filters 在持久化前 redaction；
- missing export adapter 时在创建孤儿 PENDING record 之前 fail-closed；
- export request 本身写 Audit。

生产异步 worker、加密结果对象、短时 signed URL、下载时权限复核和下载 Audit 仍为 `NODE65-GAP-304`。

## 11. Redaction

禁止 Audit / Governance reason 默认记录：

```text
password
raw API key
session secret
payment card
full Authorization header
full presigned URL query
private key
secret-shaped token values
```

实现包含：

- recursive key redaction；
- Prompt/content hash；
- URL query/fragment stripping；
- bytes hash；
- Bearer、`sk-`、GitHub token、AWS access-key ID、JWT-shaped free-text scrub。

NODE-64 Platform Admin reason 在本分支也复用同一 free-text scrubber。

## 12. Agent Audit

Agent actor记录：

```text
agent id/version
run/task
human initiator
Tool write operations
constraint overrides (若允许)
```

`AGENT` actor 必须有 `agent_run_ref + agent_version + human_initiator_user_id`；禁止以 `system` 作为模糊 actor identity。

全量 Agent/Tool producer ingress 仍属于 `NODE65-GAP-302`。

## 13. Tests / Validation

Dedicated NODE-65 gate覆盖：

- append-only；
- permission；
- recursive redaction + free-text secret scrub；
- agent actor；
- retention candidate；
- legal hold blocks deletion；
- deletion deactivation + object/search propagation；
- Hold-after-request race；
- export fail-closed / filter redaction；
- legacy audit normalization；
- ORM / Alembic contract parity；
- PostgreSQL UPDATE/DELETE direct rejection；
- API regression。

Hosted executed-green 证据仍必须获得后才能关闭 `NODE65-GAP-308`。

## 14. 验收标准

- [ ] 高风险动作都有真实 canonical Audit（P0：producer ingress 尚未全部接入）。
- [x] Audit不能普通修改/删除（core + DB trigger）。
- [x] Audit core 不保存 raw secrets，reason/filter/content 有 redaction/hash contract。
- [x] retention classes 与 policy version 技术模型明确。
- [x] deletion/hold 技术核心路径存在并 fail-closed。
- [x] audit export 核心权限/请求/redaction contract 存在。
- [ ] production Governance factory / workers / sweeper / unified security query 已完成。
- [ ] Hosted CI + production-like E2E executed green。

## 15. Definition of Done

```text
audit pipeline + governance services implemented
+ mandatory producer ingress wired
+ production deletion/export/retention adapters composed
+ redaction/retention/hold tests green
+ hosted production-like evidence green
+ all P0 gaps closed
```

**当前 Definition of Done 未满足。** NODE-65 保持 `CORE IMPLEMENTED / VALIDATING / NOT COMPLETE`。

待全部 P0 关闭后，Phase 8 才能正式进入下一节点：NODE-66 Security Hardening。

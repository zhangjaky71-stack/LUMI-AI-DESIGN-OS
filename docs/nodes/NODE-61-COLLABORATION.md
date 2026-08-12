# NODE-61 — Collaboration Engine

> Phase: 8 SaaS & Collaboration  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P1 / PRODUCT MATURITY  
> Depends on: NODE-16, NODE-40, NODE-42, NODE-52  
> Produces: Presence、Comments、Mentions、共享编辑协议、WebSocket协作层与冲突策略

---

## 1. 目标

让 Designer、Marketing、Manager、Client 和 AI Agent 能在同一 Project 协作。实时协作必须建立在 Design IR/Artifact 版本系统之上，不允许 CRDT 或 WebSocket 临时状态反客为主成为业务唯一真相。

## 2. 协作能力分层

### P0/P1 基础协作

```text
project sharing
member roles
comments
mentions
review threads
presence
selection/cursor awareness
```

### P1 实时编辑

```text
concurrent canvas edits
optimistic local operations
reconnect/rebase
conflict indication
```

## 3. Presence

Presence 是 ephemeral：

```text
user_id
project_id
document_id
cursor?
selection_ids[]
active_frame_id?
last_seen
```

存 Redis/Realtime layer，不进入 Design IR，不长期审计每个鼠标坐标。

## 4. Transport

P1 使用 WebSocket 或可替换 realtime transport：

```text
Browser
↔ Collaboration Gateway
↔ Presence / Operation fanout
↔ Design Operation API
```

业务 write仍需服务端授权、version/constraint验证。

## 5. CRDT Boundary

可使用 Yjs/CRDT 处理 collaborative view/edit synchronization，但：

```text
CRDT runtime state ≠ canonical Design IR history
```

服务端定期/按operation把协作变化归一化为 Design Operations/DesignDocumentVersion。CRDT data type不渗透 Agent、Artifact、Export contract。

## 6. Comments

Comment 绑定：

```text
Project
ArtifactVersion
DesignDocumentVersion
Node ID
Frame ID
Canvas coordinate/region
```

若Node后来删除，comment仍能通过version snapshot查看历史上下文。

## 7. Threads

```text
OPEN
RESOLVED
REOPENED
```

支持mention、reply、resolve。编辑/删除comment保留audit event。

## 8. Permissions

Viewer：查看/comment按策略；Editor：设计编辑；Approver由 NODE-62 permission；Guest link如果实现必须独立token/expiry权限。

Presence信息只广播给有同Project访问权的用户。

## 9. Concurrent Edit

P0策略：optimistic version + explicit conflict。

P1 realtime：

- 不冲突不同node ops可合并；
- 同property同时改采用明确策略（operation sequence/CRDT last-writer with metadata）并可显示“某人更新了此属性”；
- Hard constraints始终server enforcement。

## 10. Agent Collaboration

AI Agent表现为可识别actor：

```text
actor_type=AGENT
agent_run_id
```

用户可以在comment/command里 @LUMI 请求处理线程，但Agent不能自动拥有评论者没有的权限。

## 11. Notifications

事件：mention、comment reply、approval request、artifact ready。P0站内；email adapter可选。通知内容避免把敏感资产直接放邮件。

## 12. Reconnect

WebSocket断线：

```text
buffer safe local ops
→ reconnect
→ get canonical version
→ rebase/resolve
```

冲突不能静默丢本地编辑。

## 13. Tests

- 2 users不同node并发；
-同property冲突；
- presence tenant isolation；
- comment绑定旧version；
- mention permission；
- reconnect/rebase；
- Agent actor audit；
- CRDT state重启后canonical恢复。

## 14. 验收标准

- [ ] Team成员可同时查看Project。
- [ ] Presence/comments/mentions可用。
- [ ] Realtime状态不成为唯一真相。
- [ ] Hard constraints并发时仍执行。
- [ ] reconnect不丢数据。
- [ ] Agent身份与人类身份可区分。

## 15. Definition of Done

```text
collaboration backend + UI implemented
+ multi-user E2E green
+ reconnect/conflict tests green
```

下一节点：NODE-62 Approval Engine。

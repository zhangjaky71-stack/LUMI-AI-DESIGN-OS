# NODE-61 — Collaboration Engine

> Phase: 8 SaaS & Collaboration  
> Status: CORE IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P1 / PRODUCT MATURITY  
> Depends on: NODE-16, NODE-40, NODE-42, NODE-52, NODE-55, NODE-59  
> Produces: durable Comments/Threads、Mention Outbox、ephemeral Presence contract、Workspace collaboration UI、安全协作边界

---

## 1. 目标

让 Designer、Marketing、Manager、Client 和 AI Agent 能在同一 Project 协作。实时协作必须建立在 Design IR/Artifact 版本系统之上，不允许 CRDT、Presence 或 WebSocket 临时状态反客为主成为业务唯一真相。

## 2. 当前实现基线

本节点已经实现可审查的 collaboration core：

```text
Project access fence
→ exact ArtifactVersion thread
→ durable Comment / CommentRevision
→ optional Design Node anchor
→ Mention validation + Outbox IDs
→ Workspace CommentsPanel
```

Presence 当前为明确的 ephemeral contract：

```text
heartbeat = 10s
TTL = 30s
persistent DB table = none
production Redis adapter = pending
realtime gateway = pending
```

## 3. Presence

Presence 是 ephemeral：

```text
user_id
project_id
artifact_version_id?
current_frame_id?
cursor?
selection_ids[]
last_seen
```

关键安全约束：

- `user_id` 只能来自认证 actor；
- heartbeat 不接受 `display_name/avatar_url`；
- display name 从 `users + organization_members` 服务端读取；
- avatar 在没有 canonical profile source 前保持空；
- Presence 不进入 Design IR，不写 PostgreSQL 长期表；
- 当前 test/dev adapter 为 TTL in-memory，production Redis composition 仍是 P0 gap。

## 4. Durable Comments / Threads

新增 canonical PostgreSQL resources：

```text
comment_threads
comments
comment_revisions
```

Thread 固定绑定：

```text
organization_id
project_id
artifact_id
artifact_version_id   # exact, immutable context
design_node_id?
x/y?
status
```

Comment edit/delete 通过 revision + `If-Match` 做 optimistic concurrency fence；删除后的公开投影只显示 `[deleted]`，revision audit 仍保存原快照供授权审计。

## 5. Historical Context / Re-anchor

当用户打开新的 ArtifactVersion 时，旧 thread 不自动迁移：

```text
old exact version
→ historical thread
→ needs_reanchor=true
→ user review required
```

Workspace 已将当前版本与历史 thread 分离展示，并标记 `NEEDS RE-ANCHOR`。显式 reviewed re-anchor command 尚未实现，继续列 P0 gap。

## 6. Mentions / Notifications

Mention 只能指向：

- 当前 organization member；
- 且是 Project creator 或 `project_members` 显式成员。

Mention 与 Comment/Revision 在同一数据库事务内写入 Outbox。Outbox payload 只携带 project/thread/comment/user IDs，不复制评论正文，降低通知管道扩大敏感内容暴露面的风险。

Mention picker 与真实通知 consumer/delivery UX 尚未完成。

## 7. Project Permissions

Collaboration access fail-closed：

```text
organization member
AND
(project creator OR explicit project_members member)
```

角色：

- `viewer`：读取 + 评论；
- `editor`：评论 + thread resolve/reopen + Design edit permission projection；
- `admin`：管理型协作操作；
- thread creator 可 resolve/reopen 自己的 thread。

浏览器尚未完整投影角色以预先隐藏所有无权限控件，因此仍保留 role-aware UI gap；服务端拒绝始终是最终边界。

## 8. Canvas / Design Truth Boundary

Collaboration router **没有任何 DesignDocument mutation endpoint**。

所有设计编辑仍必须进入 NODE-55：

```text
Browser collaboration intent
→ Canvas DesignOps API
→ server authorization
→ version fence
→ constraints
→ canonical DesignDocumentVersion
```

Presence/Comments 不能绕过 Hard Constraints，也不能自行成为 Canvas canonical history。

## 9. Realtime Transport

Canonical 目标仍是：

```text
Browser
↔ authenticated Collaboration Gateway
↔ Redis Presence / operation fanout
↔ Design Operation API
```

当前只完成 request/response + polling core。WebSocket/SSE、disconnect cleanup、fanout ordering、reconnect/rebase、backpressure 和生产 Redis adapter 尚未闭合，因此 NODE-61 不能宣称完整 realtime collaboration。

## 10. Workspace UI

Workspace Inspector 已挂载：

- current exact version comments；
- selected Canvas node 作为新 thread 的可选 anchor；
- reply；
- resolve/reopen；
- historical threads；
- `NEEDS RE-ANCHOR` 提示。

尚未开放：mention picker、comment edit/delete/audit UI、角色驱动 controls、显式 re-anchor command、Presence avatars/cursors。

## 11. Agent Collaboration

AI Agent 后续可以作为可识别 actor 参与协作，但当前 core 不允许 Agent 通过 Comments/Presence 获得额外设计权限。Agent comment execution / `@LUMI` thread command 尚未纳入本节点完成范围。

## 12. Tests / Static Acceptance

当前证据覆盖：

- Presence TTL / expiry；
- Presence 无 durable SQL model；
- server-authoritative presence identity；
- exact ArtifactVersion comment binding；
- historical version 不自动改写；
- deleted public projection + durable revision audit；
- Comment edit/delete `If-Match`；
- Project membership fail-closed；
- Mention access + body-free Outbox；
- Thread resolve 不触碰 Artifact approval；
- Collaboration routes 无 Design mutation bypass；
- Workspace CommentsPanel exact-version mounting。

专用 static validator：`tools/node61/validate_collaboration.py`。

## 13. 开放 P0

以 `reports/nodes/NODE-61/gap-ledger.json` 为准，主要包括：

- production Redis PresencePort；
- authenticated realtime transport；
- role-aware collaboration controls；
- mention picker + notification delivery；
- comment edit/delete/audit UI；
- realtime multi-user Canvas conflict UX；
- explicit re-anchor；
- pagination / retention / privacy operations；
- Browser + PostgreSQL + Redis multi-user E2E；
- Hosted GitHub Actions executed green。

## 14. 验收状态

- [x] Team 成员通过 canonical Project access fence 协作。
- [x] Durable comments/threads 与 exact ArtifactVersion 绑定。
- [x] Mentions durable + permission validated，Outbox 不复制正文。
- [x] Presence 生命周期为 ephemeral，未成为 DB/Design 真相。
- [x] Collaboration 不创建 DesignOps bypass。
- [x] Workspace 已挂载 durable CommentsPanel。
- [ ] Production Redis/WebSocket realtime presence 可用。
- [ ] Reconnect/rebase 与多用户冲突 E2E 通过。
- [ ] Realtime Canvas collaboration 在 Hard Constraints 下验证。
- [ ] 完整角色 UI / mention / edit-delete / re-anchor UX 完成。
- [ ] Hosted CI 执行真实步骤 green。

## 15. Definition of Done

当前不满足完整 DoD：

```text
collaboration core implemented
+ durable comments UI mounted
+ safety/static contract tests authored
BUT
production realtime + multi-user E2E + Hosted green remain open
```

因此状态保持 **NOT COMPLETE**。

下一节点：NODE-62 Approval Engine。

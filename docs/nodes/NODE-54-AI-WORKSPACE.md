# NODE-54 — AI Design Workspace

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE UX  
> Depends on: NODE-28, NODE-33, NODE-42, NODE-52  
> Produces: Chat + Canvas 主工作区、输入/引用/Streaming、Stop/Resume/Retry、Approval cards

---

## 1. 目标

构建 LUMI 核心工作台：用户在同一个项目中通过自然语言驱动Agent，同时看到Canvas、任务进度、产物和审批，而不是在聊天与设计工具之间来回切换。

## 2. Desktop Layout

```text
┌──────────────┬─────────────────────────────┬─────────────┐
│ Agent/Chat   │          Canvas             │ Inspector   │
│              │                             │ /Context    │
└──────────────┴─────────────────────────────┴─────────────┘
```

左/右面板可collapse/resizable；Canvas始终保留足够空间。

## 3. Prompt Composer

支持：

- multiline；
- @ asset/artifact/frame引用；
-附件；
- selected canvas nodes自动形成context chips；
- send/stop；
- slash commands P1。

输入中明确显示当前选中了什么，避免误改。

## 4. Message Model

UI消息区分：

```text
user message
agent status/update
agent answer
artifact card
approval card
warning/error
```

不渲染内部Chain-of-Thought；展示安全、可理解的计划/进展摘要。

## 5. Streaming

SSE连接 AgentRun：

- reconnect with Last-Event-ID；
- event dedupe；
-断线状态；
-流结束从API refetch canonical run state。

UI不能把SSE作为唯一真相。

## 6. Run Control

```text
Start
Stop/Cancel
Pause（若后端支持状态）
Resume
Retry failed task
```

按钮显示操作语义，取消不假装能撤销已提交第三方任务。

## 7. Artifact Cards

消息中产物：

- preview；
- version；
- “放到Canvas”；
- compare；
- approve；
- use as reference。

所有操作绑定exact version。

## 8. Selection Context

Canvas selection变化时 composer显示：

```text
2 selected
- Hero Product [locked identity]
- Headline
```

用户说“只改这个”时 request payload传selected node IDs + document version。

## 9. Approval Card

展示：

- Agent需要确认什么；
-候选方向/Artifacts；
-影响/预计成本可选；
- Approve/Reject/Request Changes。

卡片过期/stale时禁止提交旧decision。

## 10. Warnings

明确显示：

```text
budget near limit
provider unavailable fallback
hard constraint blocked
asset rights unknown
validation requires review
```

## 11. Context Transparency

P1可展示“本次使用：Brand Kit X / 3 references / selected frame”，但不暴露秘密system prompt。

## 12. Mobile

移动端P0提供Project/Chat/preview/approve；完整Canvas专业编辑桌面优先。不要为了移动端强塞三栏。

## 13. Tests

- SSE reconnect；
- duplicated event；
- stop；
- approval stale；
- selected-node edit context；
- artifact exact version；
- provider warning；
- error recover。

## 14. 验收标准

- [ ] Chat与Canvas同Project工作区。
- [ ] Streaming可重连。
- [ ] selected objects能进入Agent command。
- [ ] run control可用。
- [ ] approval嵌入工作流。
- [ ] 不显示私有chain-of-thought。

## 15. Definition of Done

```text
workspace E2E with MockAgent green
+ SSE/recovery tests green
+ selected-edit UX green
```

下一节点：NODE-55 Infinite Canvas UI。

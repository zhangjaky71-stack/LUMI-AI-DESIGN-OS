# NODE-12 — Event Protocol

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-09, NODE-10, NODE-11  
> Produces: 版本化 Domain Event Envelope、Outbox/Inbox 语义、Realtime 映射与 AsyncAPI/JSON Schema

---

## 1. 目标

统一 API、Agent Runtime、Worker、Realtime、Audit 之间的异步语言。系统按 **at-least-once delivery + idempotent consumer** 设计，不声称消息中间件提供神奇 exactly-once。

## 2. Event Envelope

```json
{
  "event_id": "uuidv7",
  "event_type": "artifact.version.created",
  "event_version": 1,
  "occurred_at": "2026-08-12T00:00:00Z",
  "organization_id": "...",
  "workspace_id": "...",
  "project_id": "...",
  "actor": {
    "type": "user|agent|system",
    "id": "..."
  },
  "correlation_id": "...",
  "causation_id": "...",
  "trace_id": "...",
  "payload": {}
}
```

非适用 scope 字段可 null；`organization_id` 对租户业务事件通常必填。

## 3. Naming

过去式事实：

```text
project.created
asset.upload.completed
asset.ready
agent_run.started
agent_run.waiting_user
agent_run.completed
task.started
task.completed
artifact.version.created
artifact.approved
generation.completed
cost.recorded
```

命令不伪装事件；`generate.image` 是 command/task，不是已经发生的 domain event。

## 4. Versioning

`event_type + event_version` 定义 schema。

兼容变更：添加 optional field。

破坏变更：event_version +1。

消费者必须明确支持版本；未知重大版本进 DLQ/unsupported metric，不能静默猜。

## 5. Delivery

```text
Domain transaction
  ├─ update state
  └─ insert outbox
       ↓
Outbox dispatcher
       ↓
Broker
       ↓
Consumer
       ↓
Inbox dedupe
       ↓
Handler
```

producer 在 DB commit 前不直接 publish。

## 6. Idempotent Consumer

`inbox_events` unique：

```text
(consumer_name, event_id)
```

handler 与 inbox insert 尽可能同 transaction。

## 7. Ordering

不承诺系统全局顺序。

需要实体顺序时 envelope 增加：

```text
aggregate_id
aggregate_version
```

consumer 检测 stale/out-of-order 并根据 domain policy 重排、等待或丢弃旧状态更新。

## 8. Realtime UI Events

Domain event 不等于前端 event。建立 projector：

```text
Domain Event
   ↓
Realtime Projector
   ↓
SSE/WebSocket event
```

前端事件允许聚合/脱敏：

```text
agent.status
agent.delta
task.progress
artifact.created
artifact.updated
approval.required
job.progress
budget.warning
```

不要把内部 provider payload 直接流给浏览器。

## 9. Payload 规则

- event payload 包含处理该事实所需最小数据。
- 大 binary 只放 storage ref/id。
- 不放 API secret、Authorization、完整 provider request。
- PII 最小化。
- user prompt 只有确有消费者需要时才放，且审计 retention 独立。

## 10. Broker Mapping

P0 RabbitMQ：

```text
exchange: lumi.domain
routing key: event_type
```

媒体 job queue 与 domain event exchange 分开。

## 11. Retry / DLQ

Transient：指数退避 + jitter。

Permanent schema/business error：DLQ。

DLQ message 必须包含 failure metadata，但不得把 secret stack 整包暴露。

Admin 后续提供 replay；replay 仍经过 inbox/idempotency。

## 12. AsyncAPI / Schema

输出：

```text
packages/event-schema/schemas/*.json
packages/event-schema/asyncapi.yaml
```

TypeScript/Python types 由 schema 生成或进行 schema conformance test。

## 13. Trace

`correlation_id` 通常贯穿用户 command；`causation_id` 指向直接导致当前 event 的 command/event；`trace_id` 与 OpenTelemetry/LangSmith 关联。

## 14. Audit 区别

Domain event：系统事实供业务反应。

Audit event：安全/治理不可变记录。

一个动作可能同时产生两者，但 retention、payload、访问权限不同。

## 15. 测试

- outbox atomicity；
- duplicate delivery 不重复 side effect；
- unknown version；
- ordering stale event；
- DLQ；
- event serialization round trip；
- PII/secret field denylist；
- realtime projector mapping。

## 16. 验收标准

- [ ] Envelope JSON Schema 冻结。
- [ ] P0 event catalog 完成。
- [ ] Outbox/Inbox 语义实现计划清晰。
- [ ] at-least-once/idempotent 被明确接受。
- [ ] Realtime 与 Domain Event 解耦。
- [ ] AsyncAPI/Schema 可 CI 验证。

## 17. Definition of Done

```text
event schemas committed
+ serialization tests green
+ outbox/inbox integration scenario proven
+ realtime mapping documented
```

下一节点：NODE-13 Design IR。

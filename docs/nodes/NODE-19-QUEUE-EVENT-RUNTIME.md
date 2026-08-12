# NODE-19 — Queue & Event Runtime

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / RELIABILITY  
> Depends on: NODE-03, NODE-12, NODE-18  
> Produces: RabbitMQ broker、Celery worker 基础、Outbox dispatcher、DLQ/retry、事件 consumer runtime

---

## 1. 目标

把长耗时媒体任务和可靠 Domain Event 从 HTTP/Agent 同步调用中拆出。P0 使用 RabbitMQ；媒体 job 使用 Celery 5.6 family，Domain Event 使用独立 event publisher/consumer adapter，避免把两种语义混为一谈。

## 2. 两类消息

### Job

“请执行某件事”：

```text
image.transform
video.render
asset.preview
export.package
```

可以 retry，有执行状态。

### Domain Event

“某件事已经发生”：

```text
artifact.version.created
asset.ready
```

来自 outbox，不由 consumer 改写事实。

## 3. RabbitMQ Topology

```text
exchange lumi.jobs direct
exchange lumi.domain topic
exchange lumi.dlx topic
```

Queues：

```text
lumi.media.image
lumi.media.video
lumi.media.export
lumi.asset.processing
lumi.domain.<consumer>
*.dlq
```

## 4. Celery Job Contract

Task 参数只传 IDs/小 JSON：

```json
{
  "job_id": "...",
  "organization_id": "...",
  "project_id": "...",
  "operation_id": "..."
}
```

不把几十 MB base64 放 broker。

## 5. Job State

DB `jobs` 或具体 task/generation record 是可观察状态；Celery result backend 不作为唯一业务状态。

状态：

```text
PENDING
RUNNING
RETRYING
SUCCEEDED
FAILED
CANCELLED
```

## 6. Retry Policy

Error classification：

Transient：timeout, provider 429/5xx, temporary storage。

Permanent：invalid input, unsupported format, hard constraint。

使用 exponential backoff + jitter；最大 attempts 按 job type。

视频昂贵任务 retry 前查询 provider request status，防止“其实已成功”再次计费。

## 7. Celery Ack

需要重投递的 task 必须设计幂等。`acks_late` 等设置只能在 NODE-20 idempotency 成熟后针对 job 开启，不把 broker ack 当 exactly-once。

## 8. Outbox Dispatcher

循环：

```text
SELECT unpublished outbox batch FOR UPDATE SKIP LOCKED
→ publish
→ mark published_at
```

publish 与 mark 间崩溃可能重复，因此 consumer inbox 去重是必需。

## 9. Consumer Runtime

每 consumer：

```text
schema validate
→ inbox dedupe
→ authorization/scope sanity
→ handler
→ commit inbox + effect
→ ack
```

永久失败送 DLQ。

## 10. Backpressure

- queue depth metrics；
- media worker concurrency 独立；
- video queue 不挤占 image preview；
- org/project 并发限制后续 Cost/Quota 接入。

## 11. Cancellation

业务 cancel 标记写 DB；worker 在安全 checkpoint 检查。不要只依赖强杀 Celery process。

无法取消的第三方 provider job 记录 `CANCEL_REQUESTED`，结果回来后根据 policy 丢弃/不发布而非假装 provider 已取消。

## 12. Dead Letter

DLQ item 必须可在 Admin 查看：

```text
message/event id
consumer/job type
error category
attempts
first/last failure
trace id
```

P0 提供 CLI replay；NODE-64 Admin 做 UI。

## 13. Security

- broker 不公网暴露。
- credentials per environment。
- payload 不带 provider secret。
- consumer 不信任 broker payload，仍 schema validate。

## 14. Tests

- worker task success；
- transient retry；
- permanent DLQ；
- duplicate domain event；
- dispatcher crash window duplicate；
- worker crash/redelivery；
- cancellation；
- queue separation。

## 15. 验收标准

- [ ] Job 与 Domain Event 分离。
- [ ] RabbitMQ topology 可重复声明。
- [ ] Celery worker 可处理 sample job。
- [ ] Outbox dispatcher 发布 event。
- [ ] Inbox 防重复。
- [ ] retry/DLQ 可测试。
- [ ] binary 不进入 broker。

## 16. Definition of Done

```text
broker runtime implemented
+ job worker green
+ outbox/inbox integration green
+ retry/DLQ failure injection green
```

下一节点：NODE-20 Idempotency。

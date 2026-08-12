# NODE-33 — Task Graph & Scheduler

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-10, NODE-19, NODE-27, NODE-32  
> Produces: 持久化任务 DAG、ready scheduler、并发/重试/取消/预算状态机

---

## 1. 目标

把长设计项目拆成可观察、可重试、可暂停、可并行的业务 Task DAG。Deep Agent Todo 只是内部计划，TaskGraph 才是项目级执行账本。

## 2. Task Fields

```text
id
project_id
run_id
recipe_step_id
type
status
owner_agent_key
priority
input_ref/output_ref
budget_reserved
attempt_count
max_attempts
progress
started_at/finished_at
version
```

## 3. Dependencies

`task_dependencies(task_id, depends_on_task_id, condition?)`。

DAG cycle 在插入/recipe compile 阶段拒绝。

## 4. Status

```text
PENDING
READY
RUNNING
WAITING_USER
WAITING_EXTERNAL
RETRYING
SUCCEEDED
FAILED
CANCEL_REQUESTED
CANCELLED
SKIPPED
```

## 5. Ready Calculation

Task READY 条件：

- 所有 required dependencies 成功/满足 join policy；
- 项目/run 未 paused/cancelled；
- budget 可 reserve；
- concurrency slot 可用；
- required capability available。

## 6. Scheduler

P0 DB-driven scheduler：

```text
select ready candidates
FOR UPDATE SKIP LOCKED
→ claim
→ create execution command/job
```

多个 scheduler instance 不重复 claim。

## 7. Owner

Task owner 可以：

```text
DETERMINISTIC_SERVICE
AGENT:<key>
MEDIA_WORKER
HUMAN
```

## 8. Progress

0-100 只在有真实定义时用；Agent 长任务优先离散 stage：

```text
PLANNING
RESEARCHING
GENERATING
EVALUATING
WAITING_APPROVAL
```

UI 不显示虚假“87%”。

## 9. Retry

Task retry policy 包含：

```text
max_attempts
retryable_error_categories
backoff
```

同一 logical Task 保留 attempt history；副作用由 operation id 幂等。

## 10. Dynamic Tasks

Agent 可提出新的子任务，但必须经过 TaskGraphService：

- schema；
- max dynamic depth/count；
- budget；
- allowed task types；
- no cycle。

防止 Agent 无限扩任务。

## 11. Cancellation

Parent cancel policy：

```text
CASCADE_PENDING
REQUEST_RUNNING_CANCEL
```

Artifact 已完成不删除；只停止后续任务。

## 12. Parallel Budget

在 parallel fan-out 前先 reserve upper bound，避免 20 个并发 task 同时认为预算够。

## 13. Event

```text
task.created
task.ready
task.started
task.waiting
task.progress
task.succeeded
task.failed
task.cancelled
```

## 14. API/UI

Project Timeline 从 TaskGraph query，而不是解析 LangSmith trace。

## 15. Tests

- cycle；
- ready transitions；
- concurrent claim；
- dependency fail；
- retry；
- dynamic task limits；
- budget fanout；
- cancel cascade；
- resume external/user wait。

## 16. 验收标准

- [ ] Recipe 可实例化 DAG。
- [ ] scheduler 并发不重复 claim。
- [ ] Task 状态可恢复。
- [ ] Agent 动态扩展有上限。
- [ ] parallel budget 安全。
- [ ] Timeline 可直接查询。

## 17. Definition of Done

```text
task graph service + scheduler implemented
+ concurrency/cycle tests green
+ mock recipe execution green
```

下一节点：NODE-34 Context Engine。

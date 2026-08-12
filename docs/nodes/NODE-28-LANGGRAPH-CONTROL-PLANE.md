# NODE-28 — LangGraph Control Plane

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-20, NODE-22, NODE-25, NODE-27, NODE-32/33 contracts  
> Produces: 版本化主 Graph、Checkpoint/Resume、Interrupt、Streaming、Recovery 与 Run State

---

## 1. 目标

LangGraph 是 LUMI Agent 生命周期最高控制平面。它负责确定性流程、持久化执行状态、Human-in-the-loop、失败恢复与事件流；Deep Agents 作为 Graph 中的自主执行单元。

LangGraph 当前核心能力包括 durable execution、persistence、streaming 与 HITL；生产必须使用 durable checkpointer，而不是 InMemorySaver。

## 2. Graph Boundary

```text
HTTP command
→ create AgentRun domain record
→ start LangGraph thread
→ deterministic nodes / deep-agent nodes
→ interrupt / side effect / worker
→ finalize domain result
```

Graph State 不替代业务 DB。

## 3. Thread Mapping

P0：每个 `AgentRun` 一个 LangGraph `thread_id`。

```text
agent_run.id ↔ langgraph.thread_id
```

Project 的长期聊天/记忆通过 domain/memory 映射，不把整个 Project 永远塞一个超长 thread。

## 4. Run State V1

```python
class LumiRunState(TypedDict):
    run_id: str
    organization_id: str
    project_id: str
    task_id: str | None
    brief_version: int
    recipe_version: str | None
    current_task_ids: list[str]
    approval_id: str | None
    status: str
    context_refs: list[str]
    artifact_refs: list[str]
    budget_remaining: str
    errors: list[dict]
```

State 只放 IDs/小型结构；大型搜索结果、图片、文档写 Storage/Context store。

## 5. 主 Graph

```text
START
 ↓
validate_run
 ↓
load_project_snapshot
 ↓
select_or_load_recipe
 ↓
ensure_task_graph
 ↓
route_ready_tasks
 ├─ deterministic_task
 ├─ deep_agent_task
 ├─ side_effect_task
 ├─ media_job_wait
 └─ approval_interrupt
 ↓
collect_results
 ↓
quality_gate
 ├─ repair loop
 ├─ approval
 └─ finalize
 ↓
END
```

实际 Recipe 生成子图/任务，不把所有设计类型硬编码进一个巨型 Graph。

## 6. Node 分类

```text
PURE/DETERMINISTIC
AGENTIC
SIDE_EFFECT
WAIT_EXTERNAL
HUMAN_INTERRUPT
```

每个 Node 明确 category，以决定 retry/idempotency/test strategy。

## 7. Checkpoint

生产：PostgreSQL-backed checkpointer 或 LangSmith Agent Server 提供的持久化能力；部署选择在 NODE-72 最终固定。

要求：

- checkpoint 与 business transaction 分离；
- checkpoint 可清理/retention；
- thread 可恢复；
- checkpoint metadata 包含 graph version。

## 8. Interrupt

用于：

```text
creative direction approval
brand direction approval
external destructive tool approval
budget upgrade
ambiguous high-impact change
```

Interrupt payload 必须 JSON-serializable，只包含展示/恢复所需数据。

Interrupt 前任何 side effect 必须已经过 NODE-20 幂等保护。

## 9. Resume

API：

```text
POST /agent-runs/{id}/resume
```

resume command 先验证 actor 权限、run 当前状态、approval token/version，再向 LangGraph `Command(resume=...)`。

重复 resume 必须 idempotent。

## 10. Retry

Node retry 只针对 transient 技术错误。业务失败/constraint fail 应以结构化 state 路由，不抛异常让通用 retry 狂跑。

付费 SideEffect Node retry 始终经 idempotency gateway。

## 11. Long External Job

视频等长任务：

```text
submit job
→ persist job id
→ graph WAIT_EXTERNAL / return control
→ job.completed event
→ resume/re-enter via deterministic status node
```

不要让 Graph worker 占住进程数十分钟轮询。

## 12. Streaming

Graph events 通过 Realtime projector 映射：

```text
run.started
node.started
agent.status
agent.delta
tool.call
task.progress
approval.required
artifact.created
run.completed
```

内部 chain-of-thought 不输出；只输出安全的 status/structured progress。

## 13. Graph Versioning

每个 AgentRun 固定：

```text
graph_key
graph_version
code_git_sha
```

上线新 Graph 时旧 paused run 必须：继续旧 compatible runtime、迁移 state 或明确失败/人工处理；不能默默用新 schema resume。

## 14. Cancellation

```text
cancel requested
→ Graph checks safe point
→ cancel pending jobs where possible
→ release budget reservations
→ run CANCELLED
```

外部不可取消 provider request 仍 reconciliation。

## 15. Tests

- checkpoint/resume；
- interrupt approval；
- crash after successful node；
- side-effect duplicate prevention；
- long job wake-up；
- cancel；
- graph version mismatch；
- stream event sequence；
- tenant authorization on resume。

## 16. 验收标准

- [ ] 主 Graph 可用 MockProvider 跑通完整 run。
- [ ] 持久 checkpointer restart 后可 resume。
- [ ] HITL interrupt 可等待并恢复。
- [ ] paid side effect resume 不重复。
- [ ] Graph State 不存大 binary。
- [ ] graph version 可追溯。

## 17. Definition of Done

```text
control graph implemented
+ restart/resume failure injection green
+ interrupt E2E green
+ realtime projection green
```

下一节点：NODE-29 Deep Agents Runtime。

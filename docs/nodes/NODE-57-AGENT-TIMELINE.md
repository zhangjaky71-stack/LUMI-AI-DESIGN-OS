# NODE-57 — Agent Timeline & Run Observability UX

> Phase: 7 Frontend Product  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-28, NODE-33, NODE-54  
> Produces: Task/Run进度、状态/错误/工具/产物/成本摘要可视化

---

## 0. Implementation snapshot — 2026-08-18

Implemented on `feat/node-57-agent-timeline`:

- Structured public Timeline item model for run/task/tool/progress/approval/artifact/error/status.
- Canonical Current Stage derived from `RunControlSnapshot`, including `task_id`, next node, interrupts, error code, route, repair iteration and updated time.
- Refresh no longer depends solely on browser event memory: canonical current stage appears from GET control while durable SSE replay reconstructs public history when composed.
- Existing SSE duplicate/cursor handling remains authoritative for replay (`Last-Event-ID`, event-id dedupe, canonical refetch on stream end).
- Tool visibility is semantic and allowlisted; raw tool payload is never rendered.
- Task progress bar appears only for explicit integer `current/total`; opaque scalar progress never becomes a fabricated percentage.
- Retry/provider fallback and cost summaries appear only from explicit public fields; no inference from reasoning/timing.
- Exact ArtifactVersion Timeline actions open the corresponding Canvas version; incomplete artifact events are not clickable.
- Approval is anchored in the canonical Current Stage and keeps NODE-54 stale resume fencing.
- Backend and browser event boundaries recursively reject reasoning plus secret-like fields such as API keys, tokens, authorization, credentials, passwords, secrets and headers.
- Timeline projector still uses a strict display allowlist, so unrelated event payload fields are not serialized to UI.
- Tests cover canonical recovery, approval, real count progress, retry/fallback, exact artifacts, safe projection, secret fences, SSE replay dedupe/cursor and error code display.

Still open and therefore **not complete**: production durable replay composition, standardized producer-side public retry/fallback/cost/error-action semantics, independent canonical TaskGraph history projection, browser E2E scenarios, producer safe-summary review, and hosted green CI evidence.

## 1. 目标

让用户知道Agent“正在做哪一步、完成了什么、需要我做什么”，而不是一个不透明的长spinner。Timeline来自TaskGraph/Domain Events，不从内部chain-of-thought推断。

## 2. Timeline Items

```text
Run started
Brief prepared
Researching
Creative directions created
Approval required
Generating assets
Quality checking
Repairing
Export ready
Run complete
```

## 3. Data Source

Canonical：Task/AgentRun APIs。

Realtime：SSE projection。

重连/刷新后从Canonical state恢复，不依赖浏览器历史event buffer。

## 4. Item Model

```text
id
type
status
label
safe_summary
started/finished
task_id
artifact_refs
approval_ref
cost_summary optional
error_code
```

## 5. Tool Visibility

普通用户显示有意义动作：

```text
Searched web
Read brand guide
Generated 4 directions
Checked brand consistency
```

不显示完整内部tool payload/secrets/debug trace。高级debug只给Admin/Dev权限。

## 6. Progress

使用stage和实际子任务计数。例如“生成 2/4 张”；不要对未知Agent reasoning伪造百分比。

## 7. Errors

展示：

- 发生在哪一任务；
- 是否自动重试；
- 是否切换provider；
- 用户可做什么。

技术详情关联 request/trace id，但不暴露stack。

## 8. Cost

可选展开显示本run估算/实际cost/credits，避免刷屏。预算warning与需确认的昂贵步骤突出。

## 9. Artifacts

Timeline步骤可以嵌Artifact preview，并跳到Canvas/frame/version。

## 10. Approval

WAITING_USER步骤固定在可见位置并通知，用户处理后Timeline继续。

## 11. Filters

P1：All / Agent / Generation / Approval / Error。

## 12. Tests

- SSE duplicate/reconnect；
- task retry timeline；
- provider fallback；
- waiting approval；
- artifact jump；
- cancelled run；
- no chain-of-thought leakage fixture。

## 13. 验收标准

- [x] 长任务有结构化透明stage（core）。
- [x] Refresh后 canonical Current Stage恢复；历史需 durable replay production composition。
- [x] Error/retry/fallback UI只展示显式公共字段，不做推断。
- [x] Approval在 Current Stage 显著可见并沿用 stale fencing。
- [x] API/browser/Timeline三层不展示私有reasoning/secret tool payload。
- [ ] Durable replay production composition + browser refresh/reconnect E2E green。
- [ ] Producer safe-summary review green。

## 14. Definition of Done

```text
timeline E2E green
+ reconnect/retry scenarios green
+ safe-summary review green
```

当前未满足完整 Definition of Done，因此保持 NOT COMPLETE。

下一节点：NODE-58 Brand Kit UI。
# NODE-57 — Agent Timeline & Run Observability UX

> Phase: 7 Frontend Product  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0  
> Depends on: NODE-28, NODE-33, NODE-54, NODE-56  
> Produces: Canonical Run/Task Timeline、safe tool summaries、错误/重试/fallback、Approval、Artifact、Cost 可视化

## 1. Goal

Agent 长任务不能只显示 spinner。用户必须知道：

- 当前 Run 状态；
- 正在执行哪个 Task；
- 已完成什么；
- 真实子任务计数，例如 `2/4`；
- 是否发生 error / retry / provider fallback；
- 是否需要用户 Approval；
- 产生了哪个精确 ArtifactVersion；
- 可选成本摘要。

Timeline **只能**来自 canonical `AIWorkspaceSnapshot` / `AgentRunSnapshot` / Task summaries 以及 SSE 对 canonical snapshot 的投影，不得从 chain-of-thought 推断。

## 2. Canonical source

```text
GET /projects/{projectId}/ai-workspace
        │
        ├─ AgentRunSnapshot
        ├─ AgentTaskSummary[]
        ├─ WorkspaceMessage[]
        ├─ WorkspaceArtifact[]
        └─ WorkspaceApproval[]

SSE /agent-runs/{runId}/events
        ↓
applyWorkspaceEvent()
        ↓
canonical-shaped client snapshot
        ↓
projectAgentTimeline()
        ↓
AgentTimeline UI
```

Refresh/reconnect 后重新获取 canonical workspace；浏览器不保存独立 Timeline event log。

## 3. Safe observability contract

`AgentTaskSummary` 在保持老字段兼容的前提下增加 optional observability fields：

```text
category
safe_summary
started_at / finished_at
completed_units / total_units
artifact_version_ids
approval_id
tool_summaries[]
error { code, safe_message, retrying, request_id, provider_fallback }
cost_summary
```

这些字段只允许 user-facing summary。类型中故意不存在 raw tool args/results、system prompt、secret、stack trace、private reasoning 字段。

## 4. Frontend safety defense

`sanitizeTimelineText()` 对疑似以下内容做第二层兜底隐藏：

- system prompt；
- chain-of-thought；
- raw tool payload/result/args；
- Authorization Bearer；
- API key；
- stack trace；
- private markers。

前端兜底不能替代服务端安全投影，但可以避免错误字段直接进入 UI。

## 5. Timeline items

V1 支持：

```text
RUN
TASK
MESSAGE
WARNING
ARTIFACT
APPROVAL
```

状态包括 canonical Run/Task 状态，以及 UI projection 状态：

```text
WAITING_USER
WARNING
INFO
```

## 6. Progress

只显示已知计数：

```text
completed_units / total_units
2/4
```

进度条宽度仅由明确计数计算。没有总数时不显示百分比，也不根据 Agent reasoning 猜测完成度。

## 7. Tool visibility

允许：

```text
Read brand guide
Checked product identity constraints
Generated safe candidate summaries
```

禁止：

```text
raw tool payload
raw tool result
credentials
secret headers
private prompts
reasoning traces
```

## 8. Errors / retry / fallback

失败 Task 显示：

- safe error code；
- safe message；
- retrying 状态；
- request id；
- user-safe provider fallback summary；
- retryable 时直接显示 Retry action。

Retry 仍调用 NODE-54 versioned `retryTask()` gateway，不建立 Timeline 专属 mutation API。

## 9. Approval

当前 Run 的 PENDING Approval 投影为 `WAITING_USER` 并固定在 Timeline 上方。旧 Run/stale Approval 仍可见，但不可提交旧 decision。

## 10. Artifact

Artifact Timeline item保留精确：

```text
artifact_id
artifact_version_id
version
```

支持：

- 放到 Canvas；
- 作为 Agent reference；
- 切换到 Canvas 视图。

V1 不虚假声称 AI Workspace artifact-placement adapter 与 NODE-55 Canvas operations gateway 已完全 canonical convergence；精确 Canvas node 定位仍属于该生产集成边界。

## 11. Cost

Run/Task/Approval 可携带可选 cost summary。UI 默认折叠，显示 estimated / actual / credits / budget warning，避免占据 Timeline 主流程。

## 12. Filters

已实现：

```text
All
Agent
Generation
Approval
Error
```

## 13. Deterministic validation fixtures

只在 `NODE_ENV !== production && LUMI_AI_WORKSPACE_E2E=1` 时存在：

- `project-agent-retry`：canonical failed/retryable Run，含真实 `2/4`、request id 与 fallback；
- `project-agent-cancelled`：canonical canceled Run。

这些 fixture 不应进入 production client chunks。

## 14. Tests

Unit：

- canonical projection；
- actual child-count progress；
- safe tool allowlist shape；
- unknown debug field non-projection；
- suspicious private text redaction；
- provider fallback/error/request id；
- sticky Approval；
- refresh deterministic reconstruction。

Browser：

- SSE duplicate delivery；
- streamed stages；
- waiting approval；
- provider fallback filter；
- failed task retry；
- canonical refresh restore；
- canceled Run；
- ArtifactVersion Canvas handoff；
- no private execution payload leakage。

## 15. Definition of Done

NODE-57 只有在以下条件全部满足后才能标记 COMPLETE：

```text
static architecture gate green
+ typecheck green
+ unit tests green
+ production build green
+ Agent Timeline E2E green
+ NODE-54/55/56 regressions green
+ hosted pinned jobs actually executed
```

GitHub Actions 如果因账户 billing/spending-limit 在 runner 启动前失败，只记录为 hosted platform blocker，不算 PASS，也不算代码测试失败。

## 16. Current verdict

```text
canonical timeline projection        IMPLEMENTED
safe summary/redaction boundary      IMPLEMENTED
Run/Task observability UI            IMPLEMENTED
real child-count progress            IMPLEMENTED
provider fallback/error/retry UX     IMPLEMENTED
sticky Approval                      IMPLEMENTED
ArtifactVersion timeline actions     IMPLEMENTED (Canvas exact-node jump boundary remains)
Cost collapse                        IMPLEMENTED
filters                              IMPLEMENTED
unit/browser gates                   STAGED
hosted gates                         PENDING EXECUTION
```

NODE-57 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until hosted evidence exists.

下一节点：**NODE-58 — Brand Kit UI**。

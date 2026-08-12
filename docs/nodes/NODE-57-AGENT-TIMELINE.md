# NODE-57 — Agent Timeline & Run Observability UX

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-28, NODE-33, NODE-54  
> Produces: Task/Run进度、状态/错误/工具/产物/成本摘要可视化

---

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

-发生在哪一任务；
-是否自动重试；
-是否切换provider；
-用户可做什么。

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

- [ ] 长任务有透明stage。
- [ ] Refresh后Timeline恢复。
- [ ] Error/retry/fallback可理解。
- [ ] Approval显著。
- [ ] 不泄露私有reasoning/secret tool payload。

## 14. Definition of Done

```text
timeline E2E green
+ reconnect/retry scenarios green
+ safe-summary review green
```

下一节点：NODE-58 Brand Kit UI。

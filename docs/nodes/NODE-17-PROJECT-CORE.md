# NODE-17 — Project Core

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-16, NODE-10, NODE-11  
> Produces: Project CRUD、Brief、生命周期、默认版本分支与项目访问控制

---

## 1. 目标

建立所有设计、Agent、资产、任务的项目级容器。一个 Agent run 必须属于 Project；不能出现“只有聊天 thread 没有项目真相”的系统。

## 2. Project Create

输入：

```json
{
  "name": "Coffee Rebrand",
  "workspace_id": "...",
  "brand_id": null,
  "brief": null
}
```

同一 transaction 创建：

```text
Project
+ default Artifact/Design branch metadata if needed
+ project.created outbox event
+ audit
```

## 3. Project Brief

Brief 使用结构化 contract：

```text
objective
audience
brand_context
deliverables
channels
visual_direction
copy_requirements
constraints
references
locale
notes
```

允许原始 user prompt 保存为 source input，但 Agent 后续主要依赖 Structured Brief。

## 4. Brief Versioning

每次显著修改产生 `brief_version` 或 history record，AgentRun 保存启动时 brief version，避免用户后来改需求导致历史 run 无法解释。

## 5. Project Status

```text
DRAFT
ACTIVE
PAUSED
ARCHIVED
```

- Archived 禁止新 generation，除非 restore。
- Pause 不删除已有 AgentRun；running run 是否 cancel 由明确 command 决定。

## 6. Project Settings

P0：

```text
default_locale
timezone
cost_budget_default
quality_profile
model_policy_id?
data_retention_profile
```

不要把 provider secret 放 Project settings。

## 7. Access

Project 默认继承 Workspace/Org 权限；可预留 `project_members` 做更细访问。所有 nested route 先 resolve project in current tenant。

## 8. List/Search

支持：

```text
status
workspace
created_by
updated range
cursor
```

P0 name search 可 PostgreSQL trigram/ILIKE，后续再做 semantic project search。

## 9. Archive / Restore

`DELETE /projects/{id}` P0 语义为 soft-delete/archive policy，不同步删除大量 assets。真正删除进入 retention/GC workflow。

## 10. Project Summary Projection

列表页不要 join 所有重表。建立查询 projection/聚合字段：

```text
latest_artifact_preview_id
last_activity_at
active_run_count
artifact_count
```

一致性可 eventual，不是财务真相。

## 11. Events

```text
project.created
project.updated
project.paused
project.archived
project.restored
project.brief.updated
```

## 12. Tests

- create transaction；
- authorization；
- optimistic concurrency；
- brief version；
- archive prevents new paid command；
- restore；
- list cursor；
- tenant isolation。

## 13. 验收标准

- [ ] Project CRUD 与状态转换完成。
- [ ] Structured Brief contract 存在。
- [ ] Brief 有可追溯版本。
- [ ] Project 是 Agent/Artifact/Task 的必需 scope。
- [ ] archive 不会误删资产。
- [ ] Project list 不执行灾难性 N+1。

## 14. Definition of Done

```text
project APIs + services implemented
+ lifecycle tests green
+ brief versioning works
+ authorization green
```

下一节点：NODE-18 Asset Storage。

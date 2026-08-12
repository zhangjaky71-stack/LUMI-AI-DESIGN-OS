# NODE-59 — Version History, Compare & Branch UX

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-42, NODE-55  
> Produces: Version timeline、compare、fork、restore、provenance/approval visibility

---

## 1. 目标

把 Artifact Engine 的不可变历史变成用户能理解的版本体验。用户可以放心尝试AI修改，并随时回到之前版本，而不是靠“撤销到不知道哪一步”。

## 2. Version Panel

每项：

```text
preview
version/time
creator: user/agent
summary of changes
branch
quality/approval badge
```

## 3. Semantic Summary

结构化版本显示：

```text
Headline size 68→58
Background changed
Product unchanged
```

来自semantic diff/operations，而不是让LLM随意描述。

## 4. Compare

### Design IR

- before/after属性；
- changed nodes list；
- visual side-by-side/overlay。

### Raster

- side-by-side；
- wipe slider；
- optional visual diff heatmap。

## 5. Restore

UI明确：

> 恢复会创建一个新的版本，不删除后来历史。

调用restore后branch head出现新version。

## 6. Fork

从任意版本创建分支，例如 `dark-direction`。显示branch breadcrumbs；P0不做复杂merge UI。

## 7. Approval

Approved version badge；若从approved版本继续编辑，新版本为DRAFT，旧approved仍保留。

## 8. Provenance Panel

高级信息：

```text
model/provider
agent/recipe
source assets
brand rules version
quality checks
created by
```

Prompt默认只显示安全summary/hash，不暴露内部system prompt。

## 9. Concurrency

用户正在查看v3而head变v4时显示“有更新”，不自动把当前compare目标跳走。

## 10. Tests

- restore creates new；
- fork；
- compare exact versions；
- approved immutability；
- concurrent new version；
- provenance access permissions。

## 11. 验收标准

- [ ] 用户能浏览全部有意义版本。
- [ ] compare可理解。
- [ ] restore不删除历史。
- [ ] fork可用。
- [ ] provenance可追溯且权限正确。

## 12. Definition of Done

```text
version history/compare/fork/restore E2E green
```

下一节点：NODE-60 Export UI。

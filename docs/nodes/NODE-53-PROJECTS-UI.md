# NODE-53 — Projects & New Project UX

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-17, NODE-18, NODE-52  
> Produces: Project Dashboard、创建/Brief、文件/参考输入、筛选/归档/恢复

---

## 1. 目标

让用户从产品首页真正开始设计项目，而不是只能通过API。New Project flow必须支持“用户只说一句话也能开始”，同时允许上传参考、绑定Brand、指定deliverables。

## 2. Project Dashboard

卡片/列表展示：

```text
preview
name
status
last activity
brand
active Agent run
artifact count
```

支持search、status、workspace/brand过滤、cursor pagination。

## 3. New Project Flow

P0采用轻量两步，不做十屏表单：

```text
Step 1: 你想做什么？
- natural language prompt
- attachments/references

Step 2: optional context
- Brand Kit
- deliverables
- locale
- budget/quality profile advanced
```

用户可以直接“开始”，Brief Agent后续结构化。

## 4. Attachments

使用 NODE-18 direct upload：

- drag/drop；
- progress；
- type/size错误；
- upload完成后asset状态 SCANNING/READY；
-不可用资产明确提示。

## 5. References

附件可标：

```text
product
logo
style reference
content reference
brand guide
other
```

未知允许Agent分类，但用户显式分类优先。

## 6. Brief View

创建后展示 Agent生成的Structured Brief：

- objective；
- audience；
- deliverables；
- constraints；
- assumptions。

允许编辑；显著编辑产生BriefVersion。

## 7. Archive / Restore

归档需确认；不显示“永久删除”除非后续数据删除功能明确。Restore恢复Project但不自动重启历史AgentRun。

## 8. Optimistic UI

轻量rename/status可以optimistic + version conflict rollback；创建Project/上传不可假成功。

## 9. Empty States

新用户引导给真实示例意图：品牌、海报、产品图、社媒等，但不强迫模板。

## 10. Accessibility / Responsive

Desktop优先；Project dashboard在tablet/mobile可用。新建上传区域keyboard可操作。

## 11. Tests

- create minimal prompt；
- upload refs；
- failed scanning；
- brand attach；
- rename conflict；
- archive/restore；
- org switch；
- pagination/filter。

## 12. 验收标准

- [ ] 一句话可创建Project。
- [ ] reference direct upload。
- [ ] Structured Brief可查看/编辑。
- [ ] Project list/search/filter稳定。
- [ ] archive/restore安全。
- [ ] 不要求用户先填写复杂技术参数。

## 13. Definition of Done

```text
project dashboard + creation E2E green
+ upload integration green
+ brief version UX green
```

下一节点：NODE-54 AI Workspace。

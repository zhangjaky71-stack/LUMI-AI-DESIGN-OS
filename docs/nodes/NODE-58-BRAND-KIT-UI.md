# NODE-58 — Brand Kit Product UI

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 LOVART-PARITY  
> Depends on: NODE-43, NODE-18, NODE-52  
> Produces: Logo/颜色/字体/语调/视觉参考/规则管理、Brand Guide提取审核

---

## 1. 目标

让非技术用户建立和维护Brand Kit，并把它绑定到项目/生成任务。Brand Kit不是几张参考图，而是可机器执行的BrandRuleSet。

## 2. Brand Overview

展示：

```text
brand name
logos
palette
typography
voice
visual references
rules
version/status
```

## 3. Logos

上传multiple variants：primary/secondary/monochrome/icon。设置preferred background、minimum size、safe zone。上传文件经过Asset security/rights。

## 4. Colors

Palette editor：HEX/RGB等web基础；token role。P1 print profile。颜色验证、duplicate提示、contrast preview。

## 5. Fonts

- upload licensed font；
-选择已支持字体；
- heading/body/CJK fallback；
- preview多语言。

必须显示rights/许可声明；未知授权提示。

## 6. Voice

简单表单：

```text
brand personality
preferred tone
do/don't
keywords
forbidden words/claims
locale variants
```

## 7. Visual References

添加approved和negative references，标注产品/摄影/插画/布局作用。

## 8. Brand Guide Import

上传PDF：

```text
extract proposal
→ side-by-side source citation
→ user approve/edit each group
→ publish new BrandRuleSet
```

不能一键未经审核变Hard Rules。

## 9. Versioning

修改draft，发布创建新BrandRuleSet version。历史Project/Artifact保留旧version引用。

## 10. Project Binding

Project选择Brand exact/current policy：通常启动新Run时resolve当前Published version并freeze；Run过程中不热变。

## 11. Compliance Preview

对选中Artifact运行Brand check，显示violations/score并跳到对应Canvas node。

## 12. Tests

- logo upload；
- font rights；
- brand guide proposal；
- version publish；
- project binding；
- forbidden color compliance；
- stale rule version。

## 13. 验收标准

- [ ] Logo/colors/fonts/voice/reference可管理。
- [ ] BrandRuleSet发布版本化。
- [ ] PDF提取有source和人工确认。
- [ ] Project可绑定。
- [ ] Compliance可视化。

## 14. Definition of Done

```text
brand kit UX E2E green
+ version/publish tests green
+ guide-extraction review flow green
```

下一节点：NODE-59 Versions UI。

# NODE-56 — Layers & Inspector

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-38, NODE-39, NODE-55  
> Produces: Layer Tree、属性Inspector、Constraint显示、多选/批量属性与可编辑Design IR UI

---

## 1. 目标

让用户不仅“看Canvas”，还可以精确理解和编辑结构化设计。Layers/Inspector 是 Design IR 的人类可控入口，也是 AI 操作透明度的重要界面。

## 2. Layers Tree

显示：

```text
Frame
 ├─ Group
 │  ├─ Image [Hero Product]
 │  └─ Text [Headline]
 └─ QR [locked]
```

支持：select、multi-select、rename、reorder、group、visibility、lock、collapse。

## 3. Virtualization

大document Layer tree虚拟化；搜索/选中节点滚动定位，不一次render 10k DOM rows。

## 4. Inspector Sections

按kind动态：

```text
Transform
Layout
Appearance
Typography
Image/Crop
Video
Effects
Constraints
Brand Binding
Metadata/Role
```

## 5. Transform

x/y/w/h/rotation支持单位/数字验证；连续输入debounce，Enter/blur提交；多个字段更新可Batch。

## 6. Typography

```text
font family/style/weight
size
line height
letter spacing
alignment
color
spans/basic rich text
```

只显示可用/许可字体；missing font明确warning。

## 7. Constraints UI

显示有效constraint：

- lock icon；
-来源 USER/BRAND/PROJECT/SYSTEM；
- hard/soft；
-为何不能改；
-有权限时override入口。

不能让用户误以为disable UI就是安全 enforcement，server validator仍执行。

## 8. Brand Binding

显示属性是否绑定品牌token。用户直接改已绑定属性：

```text
update token binding target
or detach binding
```

必须让用户选择/明确行为，不能悄悄破坏Brand关系。

## 9. Multi-select

显示共同值/mixed state。批量修改生成BATCH operation；hard constraint target导致整批失败时显示具体节点，可选择只应用可编辑节点需要用户明确操作。

## 10. Layer Reorder

拖拽前preflight层序锁定。跨parent reparent同样校验。

## 11. Semantic Role

高级模式可查看/修改 role（Headline/Product/Logo等），改变role可能影响Agent/Constraint，因此需要warning和versioned operation。

## 12. Tests

- tree sync selection；
- reorder；
- virtual large tree；
- mixed multi-select；
- locked field；
- brand detach；
- batch fail details；
- version conflict。

## 13. 验收标准

- [ ] Layer tree与Canvas双向selection。
- [ ] 常用Design IR属性可编辑。
- [ ] Constraint来源清晰。
- [ ] Brand binding不被静默破坏。
- [ ] 10k layer tree通过virtualization基准。

## 14. Definition of Done

```text
layers/inspector implemented
+ selection/property E2E green
+ large-tree perf green
```

下一节点：NODE-57 Agent Timeline。

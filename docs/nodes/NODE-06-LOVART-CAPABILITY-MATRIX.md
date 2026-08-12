# NODE-06 — Lovart Capability Matrix

> Phase: 0 Benchmark Before Build  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-05  
> Produces: 合法、可复验的竞品能力基准与 LUMI 验收矩阵

---

## 1. 目标

将“做一个类似 Lovart.ai 的产品级系统”从模糊目标转化为可测试能力列表。只研究公开产品行为、公开文档和公开营销能力，不复制其专有代码、模型权重、商标、视觉资产或未公开实现。

## 2. 公开基准范围

截至 Architecture V2 规划期，Lovart 官方公开产品重点包括：

- 自然语言 Brief 到完成资产的 Agent 工作流；
- 自动选择不同图像/视频模型；
- Infinite / ChatCanvas 类统一工作区；
- Touch Edit / 局部修改；
- Brand Kit 与品牌一致性；
- 图片、视频、营销套件等多类输出；
- 多尺寸/批量变体；
- 多格式导出；
- Autonomous 与 Guided collaboration 两种交互方式；
- 项目/版本/Canvas 上的持续迭代。

实现阶段必须重新通过官方网页/文档核验当日产品能力，并在矩阵中记录 `observed_at`。

## 3. Matrix Schema

```yaml
capability_id: CAP-CANVAS-001
category: Canvas
name: Infinite canvas
source_type: official_docs
source_url: "..."
observed_at: 2026-08-12
competitor_status: confirmed
lumi_target: parity
lumi_phase: 7
acceptance_suite: canvas-infinite-v1
notes: ""
```

## 4. 能力类别

### A. Agent / Workflow

```text
A01 Natural-language brief
A02 Research before design
A03 Autonomous planning
A04 Guided mode
A05 Multi-step project execution
A06 Task progress visibility
A07 Continue/refine conversation
A08 Model/tool auto-selection
```

### B. Canvas / Editing

```text
B01 Infinite canvas
B02 Multi-artifact workspace
B03 Drag/select/resize/rotate
B04 Layers
B05 Local/touch editing
B06 Text editing
B07 Layout editing
B08 Version comparison
B09 Zoom/pan/navigation
B10 Reference assets on canvas
```

### C. Generation

```text
C01 Text/image generation
C02 Image editing
C03 Product scene generation
C04 Video generation
C05 Variants
C06 Resize/adaptation
C07 Mockup workflow
C08 Mixed-model routing
```

### D. Brand

```text
D01 Brand asset upload
D02 Colors
D03 Fonts
D04 Logo rules
D05 Tone/style memory
D06 On-brand generation
D07 Cross-surface consistency
```

### E. Production / Export

```text
E01 High-res export
E02 PNG/JPEG/WebP
E03 SVG where structurally possible
E04 PDF
E05 Print settings/bleed where implemented
E06 Layered/editable project export where feasible
E07 Batch export
```

### F. Project / Collaboration

```text
F01 Projects
F02 Asset organization
F03 History
F04 Team sharing
F05 Comment/review
F06 Approval
```

### G. Platform / SaaS

```text
G01 Account/workspace
G02 Credits/usage
G03 Billing
G04 Reliability/recovery
G05 Safety/rights metadata
```

## 5. Target Labels

每项能力必须标：

```text
PARITY      = LUMI 必须达到公开基准
SUPERSET    = LUMI 目标更强
DEFER       = 产品级系统不影响首发，可 P1/P2
OUT-OF-SCOPE= 不符合 LUMI 战略或法律/成本约束
```

## 6. LUMI 重点 SUPERSET

LUMI 不仅做表面功能对照，以下设计为自有工程优势：

- Design IR / DSL 可版本化；
- Constraint Engine 机器级“不要动”；
- Artifact/Provenance Graph；
- Benchmark Release Gate；
- Model Gateway 可插拔；
- Tool/MCP Gateway；
- 可审计 Cost Ledger；
- Agent/Skill/Recipe Registry；
- Sandbox + Side Effect 幂等执行。

## 7. 验收场景映射

每项 parity 能力必须至少映射一个 test/eval case，例如：

```text
Touch Edit
→ fixture: poster-with-product-logo-qr
→ command: 只把背景改成黑色
→ expected:
   product identity unchanged
   logo unchanged
   QR geometry unchanged
   background changed
```

## 8. Evidence 标准

证据优先级：

1. 官方 docs；
2. 官方 features/product page；
3. 官方发布说明；
4. 产品公开可操作 UI 观察；
5. 二手评测仅作为补充。

禁止仅根据 SEO 转载文章认定功能已存在。

## 9. Gap Report

矩阵生成：

```text
Confirmed competitor capability
       ↓
LUMI target
       ↓
Current implementation status
       ↓
Gap
       ↓
Owning NODE
```

输出至少：

- `docs/product/COMPETITOR-CAPABILITY-MATRIX.md`
- `evals/datasets/product-parity/*.yaml`

## 10. 验收标准

- [ ] 至少覆盖 A～G 七大类。
- [ ] 每个公开竞争能力有来源和观察日期。
- [ ] 所有 PARITY 项映射 owning Node。
- [ ] 所有关键项有 acceptance case。
- [ ] 明确区分公开事实与 LUMI 推断。
- [ ] 不复制竞争对手专有实现/内容。

## 11. Definition of Done

```text
public capability evidence collected
+ matrix versioned
+ parity targets assigned
+ eval cases linked
+ implementation nodes mapped
```

下一节点：NODE-07 Model Provider Matrix。

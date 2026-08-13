# NODE-06 — Lovart Capability Matrix

> Phase: 0 Benchmark Before Build  
> Status: **VALIDATING**  
> Implementation Status: **VALIDATING**  
> Implementation Branch: `node-06-lovart-capability-matrix`  
> Acceptance Report: `reports/nodes/NODE-06/acceptance.md`  
> Priority: P0  
> Depends on: NODE-05  
> Produces: 合法、可复验的竞品能力基准与 LUMI 验收矩阵

---

## 1. 目标

将“做一个类似 Lovart.ai 的产品级系统”从模糊目标转化为可测试能力列表。只研究公开产品行为、公开文档和公开营销能力，不复制其专有代码、模型权重、商标、视觉资产或未公开实现。

NODE-06 是**产品能力合同**，不是“已经实现这些能力”的声明。每个 `PARITY` 项必须在未来 owning Node 中获得可执行验收证据，才能从 `PLANNED` 升级为 `COMPLETE`。

## 2. 2026-08-12/13 官方复验后的公开基准范围

当前官方证据确认或官方营销材料声称的重点包括：

- 自然语言 Brief 到完成资产；
- Web Search、Thinking/Fast Mode、Chat History；
- 自动/手动模型选择、`@` 严格模型锁定、直连 Image/Video Generator；
- 内置多步骤 Skills 与从成功对话生成 Custom Skills；
- Infinite Canvas、Layer、对象历史、Generated Files、Mini Map；
- Touch Edit / 精确局部修改 / Quick AI Editing / Multi-Angles；
- Brand Kit、品牌手册解析、项目级/单次应用；
- 图片、视频、批量变体、Mockup、多尺寸适配；
- PNG/JPEG/MP4/PDF/PPTX/HTML/SVG/PSD 导出；
- Projects、资产复用、聊天历史、社区发布；
- 官方营销材料中的版本比较/恢复/分支、团队评审/审批；
- Credits、订阅、Top-up、额度规则与商业使用条款。

证据目录：`docs/product/lovart-evidence-sources.json`。

## 3. Matrix Contract

机器可读矩阵按七大类拆分：

```text
docs/product/capabilities/
├─ A-agent-workflow.json
├─ B-canvas-editing.json
├─ C-generation.json
├─ D-brand.json
├─ E-production-export.json
├─ F-project-collaboration.json
└─ G-platform-saas.json
```

每个 capability 至少：

```json
{
  "capability_id": "B10",
  "category": "Canvas / Editing",
  "name": "Semantic local Touch Edit without manual mask",
  "competitor_status": "confirmed",
  "lumi_target": "PARITY",
  "owning_nodes": ["NODE-47", "NODE-55"],
  "acceptance_case": "PARITY-B10",
  "evidence": [{"source_id": "SRC-TOUCH"}],
  "observed_at": "2026-08-12",
  "lumi_status": "PLANNED",
  "gap": "OPEN"
}
```

## 4. Snapshot v1.0.0

```text
7 categories
67 atomic capabilities
56 Lovart confirmed
9 Lovart confirmed_marketing
2 Lovart not_confirmed
56 LUMI PARITY
7 LUMI SUPERSET
4 LUMI DEFER
56 product-parity acceptance specs
```

`confirmed_marketing` 代表官方 Lovart feature/tool/blog 页面存在公开声明，但当前核心 docs 未提供同等操作细节。`not_confirmed` 仅表示本轮官方资料未找到合格公开证据，不推断竞争对手内部是否存在该能力。

## 5. Target Labels

```text
PARITY       = LUMI 必须达到公开基准，并绑定 product-parity case
SUPERSET     = LUMI 明确做得更强，由 owning Node 的专门验收证明
DEFER        = 不影响首发核心验收，后移到 P1/P2
OUT-OF-SCOPE = 不符合 LUMI 战略、法律或成本约束
```

## 6. LUMI SUPERSET

当前 v1.0.0 的 7 个 SUPERSET：

1. A10 — Versioned Skill Registry；
2. B06 — Artifact/Object immutable history + provenance；
3. B12 — Deterministic non-destructive edit branch/restore；
4. F04 — Version-bound compare/fork/restore；
5. G04 — Artifact-level rights governance；
6. G07 — Provenance / audit lineage；
7. G08 — Durable workflow recovery / resumable execution。

这些目标依赖 NODE-15、20、28、30、31、42、59、65、68 等后续工程节点。

## 7. Acceptance Mapping

所有 56 个 `PARITY` capability 必须与一个且仅一个验收 case 一一对应：

```text
evals/datasets/product-parity/v1/
├─ cases-A.json
├─ cases-B.json
├─ cases-C.json
├─ cases-D.json
├─ cases-E.json
├─ cases-F.json
└─ cases-G.json
```

NODE-06 只生成 `SPECIFIED_NOT_RUN` acceptance spec。owning Node 实现时再补真实 fixture、runner、grader、baseline/candidate 结果。

高信号场景：

```text
PARITY-B10
command:
  只把海报背景改成黑色；产品、Logo、二维码位置与尺寸必须保持不变。
expected:
  background changed
  product identity unchanged
  logo unchanged
  QR geometry unchanged
```

## 8. Evidence 标准

优先级：

1. official docs / statement / changelog；
2. official feature / tool page；
3. official blog / product update。

本节点不使用第三方 SEO 转载文章作为能力确认依据。证据 URL、tier、观察日期统一保存在 source catalog，并由 validator 约束必须属于 `https://www.lovart.ai/`。

## 9. Gap Report

人类可读完整矩阵：

- `docs/product/COMPETITOR-CAPABILITY-MATRIX.md`

机器可读 source/matrix/cases：

- `docs/product/lovart-evidence-sources.json`
- `docs/product/capability-matrix-manifest.json`
- `docs/product/capabilities/*.json`
- `evals/datasets/product-parity/v1/*.json`

当前 67 项 `lumi_status=PLANNED`、`gap=OPEN` 是正确状态；不能因为 NODE-06 写完矩阵就伪称产品已有竞争能力。

## 10. CI Contract

新增：

```bash
make product-parity-validate
```

Validator：`scripts/validate_product_parity.py`

它强制验证：

- 7 类完整覆盖；
- v1.0.0 的 67/56/7/4 计数；
- competitor evidence status 计数；
- evidence source 存在且为官方 Lovart URL；
- 每个 confirmed/marketing capability 有证据；
- 每个 capability 有 owning Node；
- 56 个 PARITY 与 56 个 acceptance case 一一对应；
- matrix/dataset version、observed_at 一致；
- NODE-06 acceptance cases 必须保持 `SPECIFIED_NOT_RUN`。

Validator 已接入 `scripts/ci-contracts`，因此 GitHub `contracts` job 是阻断门。

## 11. 测试

`evals/tests/test_product_parity_contract.py` 在 Python suite 中执行 validator，并确认关键计数输出：

```text
categories=7
capabilities=67
PARITY=56
SUPERSET=7
DEFER=4
parity_acceptance_cases=56
```

## 12. 验收标准

- [x] 覆盖 A～G 七大类。
- [x] 每个 confirmed/confirmed_marketing 竞争能力有官方来源和观察日期。
- [x] 所有 PARITY 项映射 owning Node。
- [x] 所有 56 个 PARITY 项有 acceptance case。
- [x] 明确区分 `confirmed` / `confirmed_marketing` / `not_confirmed`。
- [x] 不复制竞争对手专有实现/内容。
- [x] 机器可读矩阵版本化。
- [x] Matrix contract 接入 CI `contracts` job。
- [ ] Implementation PR 的完整 NODE-04/05 gates 全绿并归档证据。

## 13. Definition of Done

```text
public capability evidence collected       PASS
matrix versioned                            PASS
parity/superset/defer targets assigned      PASS
56 eval acceptance specs linked             PASS
implementation nodes mapped                 PASS
matrix validator implemented                PASS
CI contract gate wired                      PASS
clean implementation PR validation          PENDING
```

下一节点：NODE-07 Model Provider Matrix。

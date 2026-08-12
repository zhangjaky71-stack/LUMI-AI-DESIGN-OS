# NODE-31 — Skill Registry

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-29, NODE-30  
> Produces: 可复用设计/研究/生成 Skill 规范、版本依赖、加载器与 Skill Eval

---

## 1. 目标

把海报设计、品牌策略、图片局部编辑等“程序性知识”从 Agent 大 Prompt 中拆成可复用 Skill。Deep Agents 原生支持 Skills，LUMI 再增加版本、依赖、权限和评测。

## 2. 目录

```text
skills/
├─ poster-design/
│  └─ 1.0.0/
│     ├─ skill.yaml
│     ├─ SKILL.md
│     ├─ examples/
│     └─ fixtures/
├─ brand-strategy/
├─ moodboard/
├─ typography/
├─ image-edit/
├─ product-render/
├─ video-storyboard/
└─ export-social-kit/
```

## 3. Definition

```yaml
id: poster-design
version: 1.0.0
summary: ...
compatible_agents:
  - creative-director
  - layout-agent
required_tools: []
required_capabilities: []
input_schema: PosterDesignInput
output_schema: PosterDesignPlan
permissions: []
dependencies:
  - typography@^1
eval_profile: poster-design-v1
```

## 4. SKILL.md 内容标准

- when to use；
- required inputs；
- step sequence；
- design heuristics；
- constraints；
- verification checklist；
- failure modes；
- examples；
- what not to do。

Skill 不是随便堆“高级、极简、好看”形容词。

## 5. Loading

Context Compiler 根据：

```text
task type
recipe
agent role
available tools
brand/project context
```

选择最少必要 skills。不要把 100 个 skill 全部加载。

## 6. Versioning

Run 固定 exact versions。Skill 更新不改变已暂停 run 的语义。

Breaking output/input 或核心步骤 → major。

## 7. Dependency

构建 skill dependency DAG，禁止 cycle。Loader 统一去重依赖，顺序 deterministic。

## 8. Permissions

Skill 不能扩大 Agent permissions。即使 skill 声明需要 `sandbox.execute`，Agent config 未允许时 registry validation fail。

## 9. Examples / Copyright

Examples 必须使用自有/许可/合成 fixture，不复制竞争对手专有模板作为训练提示素材。

## 10. Skill Eval

每个生产 skill 至少：

- schema correctness；
- task success suite；
- regression samples；
- cost/latency guard；
- human review（设计类）。

## 11. 首批 P0 Skills

```text
brief-normalization
web-research
brand-strategy
creative-direction
moodboard
poster-design
typography
layout
image-generation
image-edit
product-render
visual-critique
brand-consistency
export-social
```

## 12. Tests

- dependency resolve；
- cycle；
- incompatible agent；
- permission escalation；
- exact version；
- context selected/not selected；
- eval gate。

## 13. 验收标准

- [ ] Skill schema + loader。
- [ ] 10+ P0 Skill definitions。
- [ ] dependency DAG。
- [ ] skill 不能扩大权限。
- [ ] production skill 有 eval。

## 14. Definition of Done

```text
skill registry implemented
+ first skill pack versioned
+ dependency/permission tests green
```

下一节点：NODE-32 Workflow / Recipe Engine。

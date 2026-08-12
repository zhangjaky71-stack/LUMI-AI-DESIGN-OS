# NODE-32 — Workflow / Recipe Engine

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-30, NODE-31, NODE-13/14  
> Produces: 版本化 Design Recipe DSL、编译/实例化、Approval/Gate/Parallel 结构

---

## 1. 目标

避免 Agent 每次从零发明整个业务流程。Recipe 定义稳定骨架，Deep Agents 在骨架允许范围内自主规划。

```text
Recipe = deterministic business skeleton
Agent = adaptive execution inside steps
```

## 2. Recipe Definition

```yaml
id: brand-identity
version: 1.0.0
inputs:
  - brief
steps:
  - id: research
    type: agent
    agent: research-agent@^1
  - id: strategy
    type: agent
    depends_on: [research]
  - id: moodboards
    type: foreach
    count: 3
    template:
      type: agent
      agent: moodboard-agent@^1
  - id: approve-direction
    type: approval
    depends_on: [moodboards]
  - id: logo
    type: agent
    depends_on: [approve-direction]
```

## 3. Step Types V1

```text
DETERMINISTIC
AGENT
PARALLEL
FOREACH
APPROVAL
QUALITY_GATE
MEDIA_JOB
SUBRECIPE
FINALIZE
```

任意脚本不是 Recipe type；复杂逻辑放 tested service。

## 4. Inputs / Outputs

每 step 声明 schema 和 reference binding：

```text
input:
  brief: $project.brief
  research: $steps.research.output
output_schema: BrandStrategy
```

编译时尽量检查引用存在和类型兼容。

## 5. Conditions

V1 提供受限表达式 DSL，而不是 `eval()`：

```text
if: "steps.critic.score < 80"
```

表达式 parser allowlist operations，禁止 arbitrary Python/JS。

## 6. Loops

只允许有界 loop：

```text
max_iterations
budget_limit
stop_condition
```

例如 repair loop max 2/3，防 autonomous infinite loop。

## 7. Parallel

平行步骤必须声明：

```text
max_parallel
budget split
join policy ALL|ANY|MIN_SUCCESS
```

## 8. Approval

Approval step 生成 domain Approval + LangGraph interrupt，定义：

```text
prompt summary
artifact/options refs
allowed actions
expiry?
resume mapping
```

## 9. Quality Gate

```text
metrics
thresholds
repair_recipe?
max_repair_iterations
```

不能让 Critic 自己无限重试。

## 10. Version

Project run 固定 recipe exact version。新 version 发布走 benchmark。

## 11. Compiler

```text
Recipe YAML
→ schema validate
→ dependency DAG
→ static checks
→ resolve agents/skills
→ compile TaskGraph template
→ LangGraph orchestration hooks
```

## 12. 首批 Recipes

```text
quick-image
poster-campaign
brand-identity
product-visuals
social-kit
image-edit
video-campaign
```

## 13. Security

Recipe 不能直接声明 provider key、raw URL、SQL、host command。只引用注册 Agent/Tool/Skill/Media operation。

## 14. Tests

- invalid dependency；
- cycle；
- unsafe expression；
- bounded loop；
- approval resume；
- parallel join；
- exact agent/skill resolve；
- budget propagation。

## 15. 验收标准

- [ ] Recipe DSL schema。
- [ ] 7 个首批 recipe skeleton。
- [ ] compile 到 TaskGraph。
- [ ] approval/quality/loop 有界。
- [ ] 不支持 arbitrary code eval。
- [ ] recipe exact version provenance。

## 16. Definition of Done

```text
recipe compiler implemented
+ initial recipes committed
+ static/error tests green
+ one end-to-end mock recipe green
```

下一节点：NODE-33 Task Graph。

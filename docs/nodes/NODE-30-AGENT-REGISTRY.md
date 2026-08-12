# NODE-30 — Agent Registry

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-23, NODE-25, NODE-29  
> Produces: 版本化 AgentDefinition、解析/校验/发布机制、Agent provenance

---

## 1. 目标

Agent 不散落在 Python 文件中的 Prompt 常量里。每个角色以版本化配置定义模型策略、Tools、Skills、Context、Memory、预算和 Eval profile。

## 2. Definition

```yaml
id: creative-director
version: 1.0.0
role: Creative Director
description: ...
model_policy: reasoning-high
tools:
  allow:
    - web.search
    - asset.read
skills:
  - creative-direction@^1
context_policy: creative-director-v1
memory_policy:
  read: [project, brand]
  write: [project]
budget_policy: creative-medium
permissions:
  sandbox_execute: false
output_schema: CreativeDirectionResult
eval_profile: creative-director-v1
```

## 3. Storage

P0 canonical definitions 在 Git：

```text
agents/<id>/<version>/agent.yaml
agents/<id>/<version>/system.md
```

DB 可缓存已发布 metadata。未来 UI 编辑通过 publish workflow 生成不可变版本。

## 4. Version

SemVer：

- prompt/behavior 小兼容优化：minor/patch 按团队规则；
- output schema/tool contract breaking：major。

每次 AgentRun 解析 exact version 并保存。

## 5. Resolve

```text
recipe requests creative-director@^1
→ registry resolves 1.3.2
→ checks dependencies/tools/skills/models
→ freezes exact resolved config in run provenance
```

运行中不随 registry 热更新。

## 6. Validation

发布前：

- YAML schema；
- output schema exists；
- model policy exists；
- tool permission valid；
- skill versions resolve；
- context/memory policy valid；
- benchmark profile exists；
- system prompt static lint。

## 7. Prompt Injection Boundary

System prompt 中不拼接未标记的用户/网页文本。Registry prompt 只包含可信固定 instruction，动态资料由 Context Compiler 以明确 delimiter/typed messages 注入。

## 8. Status

```text
DRAFT
CANDIDATE
PRODUCTION
DEPRECATED
DISABLED
```

Production promotion 必须经过 eval release gate。

## 9. Rollback

Router/Recipe 可以把 alias `production` 指回旧 exact version，无需修改历史 run。

## 10. Tests

- schema invalid；
- missing tool/skill；
- semver resolve；
- deprecated exact resume；
- production alias rollback；
- provenance exact freeze。

## 11. 验收标准

- [ ] AgentDefinition schema。
- [ ] Git versioned definitions。
- [ ] exact resolve/provenance。
- [ ] tool/model/skill dependencies validate。
- [ ] production promotion 需 eval。

## 12. Definition of Done

```text
agent registry loader/validator implemented
+ sample agents versioned
+ release/rollback contract green
```

下一节点：NODE-31 Skill Registry。

# NODE-43 — Brand Rules Engine

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 CORE QUALITY  
> Depends on: NODE-14, NODE-17, NODE-18, NODE-39  
> Produces: Brand Token/Rule model、Brand Context、Compliance Validator、品牌指南提取提案

---

## 1. 目标

让品牌一致性成为结构化规则，而不是 Prompt 里一句“保持品牌感”。系统要知道可用颜色、字体、Logo版本、安全区、语调、摄影风格和禁止事项。

## 2. Brand Model

```text
BrandProfile
BrandTokenSet
BrandAssetSet
BrandRuleSet
BrandVoice
BrandVisualReferenceSet
```

## 3. Tokens

```text
color.primary/secondary/accent/neutral
font.display/body/cjk_fallback
spacing scale
radius/style tokens optional
```

Tokens有 stable id/version；Design IR node可 `brand_binding`。

## 4. Logo Rules

```text
allowed_logo_assets
minimum_size
clear_space
allowed_background classes
monochrome variants
forbidden stretch/rotate/recolor
```

Logo identity hard rule可接 NODE-44。

## 5. Typography Rules

```text
allowed font assets
fallbacks
headline/body hierarchy
minimum readable size per profile
case/language rules
```

字体 rights 由 Asset metadata验证。

## 6. Color Rules

- allowed palettes；
- token usage；
- minimum contrast where required；
- forbidden colors；
- print/web profile differences。

## 7. Voice

结构化：

```text
tone attributes
do/don't examples
preferred vocabulary
forbidden claims/terms
locale variations
```

Voice是 copy agent context，不直接成为 Canvas style rule。

## 8. Visual Style

```text
photography direction
lighting
composition
background style
texture
illustration style
reference assets
negative references
```

很多属于 SOFT/ADVISORY，而不是强锁。

## 9. Rule Sources

```text
USER_EXPLICIT
APPROVED_GUIDE_EXTRACTION
MANUAL_ADMIN
INFERRED_PROPOSAL
```

从 PDF Brand Guide 自动提取只能先生成 proposal，不能未经用户/管理员批准就把推断变 hard rule。

## 10. Extraction Pipeline

```text
brand guide asset
→ Knowledge extraction
→ Brand Agent structured proposal
→ source page citations
→ human review
→ publish BrandRuleSet version
```

## 11. Brand Context

Context Engine获取 compact BrandContext：

```text
hard rules
selected tokens
allowed assets
voice summary
reference refs
rule version
```

## 12. Compliance

结构化检查：

- fonts/color/logo geometry/token bindings。

视觉检查：

- logo appearance；
- image style similarity/advisory；
- brand VLM grader。

输出 violations + score；hard violations阻止 approval。

## 13. Versioning

AgentRun/ArtifactVersion记录 exact `brand_rule_set_version`。品牌更新不追溯修改历史作品。

## 14. Tests

- token binding；
- forbidden color；
- logo safe zone；
- font unavailable；
- extraction citation；
- inferred rule cannot auto hard；
- version snapshot。

## 15. 验收标准

- [ ] Brand Kit有机器结构。
- [ ] BrandRuleSet版本化。
- [ ] hard/soft区分。
- [ ] guide extraction需审批。
- [ ] Artifact可记录品牌规则版本。
- [ ] Compliance 接 Constraint/Critic。

## 16. Definition of Done

```text
brand rule runtime implemented
+ rule fixtures/evals green
+ BrandContext integration green
```

下一节点：NODE-44 Identity Engine。

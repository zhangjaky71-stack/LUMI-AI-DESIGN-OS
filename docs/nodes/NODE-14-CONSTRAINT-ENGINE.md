# NODE-14 — Constraint Engine Specification V1

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-13, NODE-09  
> Produces: 结构化约束模型、优先级规则、pre/post validation contract、违规报告

---

## 1. 目标

把“这个不要动”“Logo 不能变”“二维码必须可扫”从 prompt 文本变成机器可执行规则。Constraint Engine 必须能在 Agent 操作前阻止明显非法操作，并在 render/generation 后验证结果。

## 2. Constraint Model

```json
{
  "id": "...",
  "type": "LOCK_POSITION",
  "scope": {"node_ids": ["qr"]},
  "severity": "HARD",
  "source": "USER",
  "priority": 1000,
  "parameters": {},
  "active": true
}
```

## 3. Severity

```text
HARD   = 默认不可违反
SOFT   = 允许但产生 penalty/warning
ADVISORY = 设计建议，不阻断
```

## 4. Source / Precedence

默认优先级：

```text
SAFETY/SYSTEM
> USER_EXPLICIT
> APPROVED_BRAND_RULE
> PROJECT_RULE
> RECIPE_RULE
> AGENT_INFERRED
> STYLE_PREFERENCE
```

同级冲突必须生成 conflict，而不是静默选一个。

## 5. Constraint Types V1

### Geometry locks

```text
LOCK_POSITION
LOCK_SIZE
LOCK_ROTATION
LOCK_TRANSFORM
LOCK_ASPECT_RATIO
LOCK_LAYER_ORDER
LOCK_PARENT
```

### Content / identity

```text
LOCK_CONTENT
LOCK_TEXT
LOCK_ASSET
LOCK_IDENTITY
LOCK_STYLE
LOCK_BRAND
```

### Region

```text
PROTECT_REGION
MUST_STAY_INSIDE
MUST_NOT_OVERLAP
MIN_MARGIN
SAFE_AREA
```

### Quality requirement

```text
REQUIRE_CONTRAST
REQUIRE_SCANNABILITY
REQUIRE_TEXT_READABILITY
REQUIRE_BRAND_COMPLIANCE
REQUIRE_RESOLUTION
REQUIRE_IDENTITY_SCORE
```

## 6. User Language → Constraint

Agent/intent parser 可以提出 constraints，但创建前结构化确认：

输入：

```text
二维码和产品都不要动，只把背景改黑色
```

输出 candidate：

```text
QR: LOCK_TRANSFORM + LOCK_CONTENT + REQUIRE_SCANNABILITY
Product: LOCK_TRANSFORM + LOCK_IDENTITY
Background: editable target
```

明确 user instruction 可自动成为 USER_EXPLICIT hard lock，无需每次弹确认。

## 7. Preflight Validation

对 Design Operation：

```text
operation
→ determine affected properties/nodes
→ load active constraints
→ evaluate
→ ALLOW | ALLOW_WITH_WARNINGS | DENY
```

例如 `MOVE_NODE qr` + `LOCK_POSITION` => DENY。

## 8. Postflight Validation

生成式编辑不能只靠 preflight。图片/视频生成后验证：

- identity similarity；
- OCR/text；
- QR scannability；
- dimensions；
- logo compare；
- brand colors；
- protected region visual diff。

结果：

```text
PASS
FAIL_REPAIRABLE
FAIL_HARD
```

## 9. Violation

```json
{
  "constraint_id": "...",
  "type": "LOCK_POSITION",
  "severity": "HARD",
  "target_id": "qr",
  "expected": {},
  "actual": {},
  "message_code": "CONSTRAINT_POSITION_CHANGED",
  "repair_hint": {}
}
```

前端显示人类语言由 message_code 本地化，不让 validator 拼 UI 文案。

## 10. Protected Region

对于像素编辑，`PROTECT_REGION` 保存 normalized rect/polygon + reference hash/feature；postflight 可做 image diff threshold。

必须容忍编码/抗锯齿小差异，不用逐像素 exact equality 作为唯一指标。

## 11. QR Scannability

验证至少：

- 可检测 QR；
- 解码成功；
- payload 与原值一致；
- quiet zone/尺寸 warning。

失败对 hard constraint 阻止 approved/export。

## 12. Override

只有有权限的用户可 override 某些非安全 hard constraint：

```text
constraint_override
reason
actor
occurred_at
```

系统安全 constraint 不允许普通用户 override。

## 13. Agent Integration

Agent 规划时收到 compact constraint summary，而不是整表 dump；执行 tool 必须再由 server-side validator 实际 enforcement。

Prompt 不是 enforcement boundary。

## 14. Constraint Snapshot

ArtifactVersion 记录生成/编辑时生效的 constraint set hash，保证后续可解释“当时为什么拒绝/通过”。

## 15. Tests

- geometry locks；
- user vs agent precedence；
- conflicting hard constraints；
- batch atomicity；
- QR postflight；
- protected region diff；
- override audit；
- stale document version；
- missing target。

## 16. Benchmark

至少建立 100 条 constraint-following cases，重点是常见设计修改：

```text
only background
keep product
keep logo
keep QR
change title size
resize frame without distorting logo
```

## 17. 验收标准

- [ ] Constraint JSON Schema。
- [ ] V1 类型全部有 evaluator contract。
- [ ] hard/soft/advisory 与 precedence 冻结。
- [ ] preflight + postflight 两阶段。
- [ ] user explicit locks 可被结构化。
- [ ] hard violation 不能写 approved version。
- [ ] override 可审计。

## 18. Definition of Done

```text
constraint spec frozen
+ validators testable
+ violation schema frozen
+ benchmark fixtures created
```

下一节点：NODE-15 Artifact / Version / Provenance。

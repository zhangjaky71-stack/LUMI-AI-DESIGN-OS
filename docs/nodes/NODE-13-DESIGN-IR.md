# NODE-13 — Design IR Specification V1

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-09, NODE-08  
> Produces: LUMI 设计中间表示 JSON Schema、Operation Schema、Fixture Corpus、兼容规则

---

## 1. 目标

Design IR 是 LUMI 最核心的自有 contract：Agent、Constraint Engine、Canvas Compiler、Artifact、Export 都通过它沟通。它必须独立于 PixiJS/React/任何模型 Provider。

原则：

```text
Agent intent
→ Design Operation
→ Design IR
→ Constraint validation
→ Canvas/Renderer
```

禁止持久化 Pixi scene object。

## 2. Document

```json
{
  "schema_version": "1.0",
  "document_id": "...",
  "unit": "px",
  "root_id": "root",
  "nodes": {},
  "resources": {},
  "metadata": {}
}
```

`nodes` 使用 ID map，避免深层 JSON patch 随 parent position 变化导致脆弱 diff；parent/children 仍明确保存顺序。

## 3. Node Common Fields

```text
id
kind
name
role
parent_id
children[]
visible
locked
opacity
blend_mode
transform
bounds
style_refs[]
constraint_refs[]
semantic
metadata
```

Transform：

```text
x, y
width, height
rotation_deg
scale_x, scale_y
skew_x, skew_y
anchor_x, anchor_y
```

所有数值必须是有限 number；NaN/Infinity 拒绝。

## 4. Node Kinds V1

```text
DOCUMENT_ROOT
FRAME
GROUP
TEXT
IMAGE
SHAPE
VECTOR_PATH
VIDEO
MASK
GUIDE
COMPONENT
INSTANCE
```

未知 kind 在同 major schema 下不能随意解析为 GROUP；必须显式兼容策略。

## 5. Frame

```text
width/height
background
clip_content
layout hints
export settings
```

一个 Project/Canvas 可有多个 Frame，支持社媒多尺寸并排。

## 6. Text

```text
content
font_family
font_asset_id?
font_size
font_weight
font_style
line_height
letter_spacing
paragraph_spacing
align
vertical_align
fill
stroke
text_transform
language
writing_direction
```

编辑器内部存语义文本 + typographic properties，不存仅 renderer 可懂的 texture。

V1 rich text 可通过 spans：

```text
spans[] {start,end,style_override}
```

必须验证 UTF-16/codepoint index 策略，避免 emoji/中文 surrogate 错位；最终 contract 明确使用 Unicode code point 或 grapheme-aware range helper。

## 7. Image

```text
asset_id
source_artifact_version_id?
crop
fit
focal_point
filters
mask_id?
identity_binding?
```

不持久化临时 presigned URL。

## 8. Shape / Vector

Shape V1：rect/ellipse/line/polygon。

VectorPath：标准化 path command list 或 SVG-compatible normalized path data；禁止执行任意 SVG script/external resource。

## 9. Video

```text
asset_id
trim_start_ms
trim_end_ms
poster_asset_id
autoplay_in_preview
mute
transform
```

时间轴高级能力后续 schema minor version 扩展。

## 10. Semantic Role

`role` 不是纯名称，用于 Agent：

```text
BACKGROUND
HERO_PRODUCT
LOGO
HEADLINE
BODY_COPY
PRICE
CTA
QR_CODE
DECORATION
REFERENCE
```

允许 custom namespaced role：`custom:*`。

## 11. Resource Refs

Document 只引用：

```text
asset_id
font_id
brand_token_id
style_id
```

资源实际二进制在 Asset/Object Storage。

## 12. Operations

Agent 不提交整文档覆盖，提交结构化 operations：

```text
CREATE_NODE
DELETE_NODE
SET_PROPERTY
MOVE_NODE
RESIZE_NODE
ROTATE_NODE
REORDER_NODE
REPARENT_NODE
REPLACE_ASSET
SET_TEXT
APPLY_STYLE
BATCH
```

每个 operation：

```json
{
  "operation_id": "...",
  "type": "SET_PROPERTY",
  "target_ids": ["headline"],
  "expected_document_version": 12,
  "payload": {},
  "reason": "user requested smaller title"
}
```

## 13. Transactional Batch

`BATCH` 默认 all-or-nothing：若任一 hard constraint fail，整 batch 不写入新 document version。

## 14. Design Diff

版本比较以 operation log + semantic diff 为主：

```text
node added/removed
property changed
geometry changed
asset replaced
text changed
constraint changed
```

不要仅比较最终 JSON 字符串。

## 15. Validation Layers

```text
JSON Schema
→ structural invariant
→ graph invariant
→ resource reference invariant
→ constraint validation
→ renderer capability validation
```

节点 parent graph 不允许 cycle。

## 16. Schema Compatibility

- `1.x`：backward compatible additions。
- `2.0`：允许 breaking。
- migration function `v1→v2` 必须 deterministic。
- Artifact 保存创建时 schema version。

## 17. Canonical Serialization

为 hash/cache/provenance：

- object key canonical ordering；
- float normalization policy；
- 不包含 ephemeral UI state；
- 输出 content hash。

## 18. UI Ephemeral State 不进入 IR

禁止保存：

```text
current hover
selection marquee
open panel
cursor location
viewport camera（除非作为单独 user view state）
DOM element id
Pixi texture id
```

## 19. Fixture Corpus

至少：

1. 单 Frame 海报。
2. 多 Frame 社媒套件。
3. Logo + QR locks。
4. 中文文本。
5. Group/mask。
6. image crop。
7. component/instance。
8. invalid cycle。
9. missing asset。
10. v1 migration fixture。

## 20. 测试

- JSON schema。
- parent-child round trip。
- operations determinism。
- batch atomicity。
- canonical hash。
- text Unicode range。
- invalid cycle。
- renderer compile fixture。

## 21. 验收标准

- [ ] V1 JSON Schema 发布。
- [ ] TypeScript + Python types 可生成/一致。
- [ ] Operation Schema 发布。
- [ ] 10+ fixtures。
- [ ] persisted IR 不依赖 Pixi/React。
- [ ] canonical hash stable。
- [ ] version migration policy 定义。

## 22. Definition of Done

```text
Design IR V1 schema frozen
+ operation schema frozen
+ TS/Python conformance green
+ fixtures committed
```

下一节点：NODE-14 Constraint Engine。

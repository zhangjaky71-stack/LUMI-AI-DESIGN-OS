# NODE-15 — Artifact / Version / Provenance Specification V1

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-09, NODE-10, NODE-13, NODE-14  
> Produces: Artifact 生命周期、版本树、血缘图、内容寻址和 Rights/Provenance contract

---

## 1. 目标

确保系统能够回答任何设计结果：

```text
它是什么？
来自哪里？
由谁/哪个 Agent 做的？
用了哪个模型/Prompt？
基于哪个版本？
用了哪些素材？
当时有哪些约束？
是否批准？
是否允许商用/分享？
```

## 2. Artifact Types

```text
DESIGN_DOCUMENT
RASTER_IMAGE
VECTOR_IMAGE
VIDEO
AUDIO
PDF
HTML
ARCHIVE
EXPORT_PACKAGE
```

`CANVAS` 不作为随意 binary 类型；Canvas 的持久真相是 DesignDocument/ArtifactVersion + user view state。

## 3. Artifact vs Version

Artifact 是逻辑作品：`Campaign Poster A`。

ArtifactVersion 是不可变快照：`v1/v2/...`。

```text
Artifact
 ├─ branch main
 │   ├─ v1
 │   ├─ v2
 │   └─ v3
 └─ branch alt-dark
     ├─ v2b
     └─ v3b
```

## 4. Version Immutability

创建 version 后：

- content hash 不变；
- file ref 不原地替换；
- metadata 更正若影响 provenance，产生 annotation/event，不篡改历史事实；
- 新编辑创建新 version。

## 5. Branch

```text
branch_id
artifact_id
name
base_version_id
head_version_id
created_by
```

P0 支持 fork/restore，不承诺复杂 Git 三方 merge；Design IR merge P1 研究。

## 6. Version Record

```text
id
artifact_id
branch_id
parent_version_id
schema_version
version_number
status
content_hash
primary_file_id?
design_document_version_id?
quality_score?
constraint_snapshot_hash
created_by_type
created_by_id
created_at
```

## 7. Lineage Edge

```text
DERIVED_FROM
EDITED_FROM
GENERATED_FROM
COMPOSED_FROM
RESIZED_FROM
EXPORTED_FROM
REFERENCE_USED
```

支持多父输入，例如一张广告由 product asset + logo + generated background 组成。

## 8. Provenance Record

至少：

```text
agent_run_id
task_id
generation_id
provider
model
provider_request_id
prompt_hash
prompt_template_version
input_asset_ids
input_artifact_version_ids
design_ir_schema_version
constraint_snapshot_hash
recipe_version
skill_versions
code_git_sha
```

敏感 prompt 内容可以单独受控存储；Artifact 只需可追溯 hash/ref。

## 9. Content Hash

文件使用 SHA-256 或经 ADR 批准的 cryptographic hash。

DesignDocument 使用 canonical serialization hash。

用途：

- duplicate detection；
- cache；
- provenance integrity；
- idempotent export。

## 10. File Model

ArtifactVersion 可以有多文件：

```text
preview
original
thumbnail
web-optimized
print-pdf
layer-data
```

每个 file：

```text
storage_key
mime_type
size_bytes
checksum
width/height
duration_ms
metadata
```

不存长期 presigned URL。

## 11. Status

```text
DRAFT
READY
APPROVED
REJECTED
ARCHIVED
```

只有 READY 通过必要 validation 后可 APPROVED。

## 12. Restore

Restore 不回写历史：

```text
select v2
→ create new v5 whose content derives from v2
→ branch head = v5
```

因此历史时间线始终可审计。

## 13. Delete

用户删除 Artifact：

- 逻辑删除/archived；
- retention window；
- background GC 只删除没有任何 live reference、没有 legal hold 的 object。

Provenance/Audit retention 独立。

## 14. Rights / Licensing

Asset/Artifact 记录：

```text
source_type
owner_assertion
license_type
commercial_use
redistribution
training_use
attribution_required
source_url/reference
review_status
```

LUMI 不自动保证第三方素材权利；UI 必须能显示来源和未确认状态。

## 15. Export Provenance Manifest

企业/高级 export package 可包含：

```json
{
  "artifact_version": "...",
  "created_at": "...",
  "sources": [],
  "models": [],
  "rights": [],
  "checksums": []
}
```

不包含 secret。

## 16. API Operations

后续 API 支持：

```text
list versions
compare
fork
restore
approve/reject
get lineage
get provenance
```

## 17. GC Safety

Object Storage GC 使用 mark-and-sweep 风格：

1. 找 DB live refs；
2. 找 retention/legal hold；
3. 标记 candidate；
4. delay；
5. 二次确认无引用；
6. delete。

禁止 DB transaction 提交后立刻同步删原文件造成恢复困难。

## 18. Tests

- version immutability；
- branch head；
- restore creates new version；
- lineage multi-parent；
- content hash dedupe；
- cross-tenant lineage rejection；
- rights inheritance policy；
- GC reference safety。

## 19. 验收标准

- [ ] Artifact/Version/Branch/Edge 模型明确。
- [ ] Version immutable。
- [ ] Fork/restore 有精确定义。
- [ ] provenance 能追到 model/prompt/task/input/code。
- [ ] 文件有 checksum。
- [ ] rights metadata 存在。
- [ ] GC 不会删除 live referenced object。

## 20. Definition of Done

```text
artifact version contract frozen
+ provenance schema frozen
+ lineage fixtures/tests ready
+ rights model documented
```

完成 Phase 1，下一节点：NODE-16 Auth / Tenant。

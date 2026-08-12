# NODE-42 — Artifact Engine Runtime

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-15, NODE-18, NODE-38  
> Produces: Artifact/Version/Branch/Lineage/Provenance 服务、比较/恢复/分叉/GC

---

## 1. 目标

实现所有设计成果的不可变版本与血缘管理，使局部编辑、生成、导出、回滚、审批都围绕 ArtifactVersion 发生。

## 2. Services

```text
ArtifactService
VersionService
BranchService
LineageService
ProvenanceService
ArtifactFileService
GarbageCollectionService
```

## 3. Create Artifact

创建逻辑作品 + main branch + v1可同 transaction完成。生成式任务可先创建 candidate Artifact/Version，成功后 READY。

## 4. Version Creation

输入：

```text
parent_version_id
content/design_document_ref
files[]
provenance
constraint_snapshot
quality summary
```

事务：

```text
verify parent/head policy
→ create immutable version
→ add lineage edges
→ update branch head optimistic
→ outbox event
```

## 5. Branch / Fork

```text
fork version v2
→ branch alt-a base=v2 head=v2
→ next edit creates alt-a:v3a
```

P0 branch name唯一于 artifact。

## 6. Restore

恢复旧版本不移动时间历史：

```text
restore(v2)
→ copy logical content ref/snapshot
→ create new head v7 derived_from v2
```

## 7. Compare

结构化设计：semantic diff from NODE-38。

Raster：生成 optional visual diff/overlay metrics。

Video：metadata + keyframe/contact-sheet comparison P1。

## 8. Provenance

每 version 必须写 exact refs：

```text
agent_run/task/generation
model/provider
prompt hash/template version
recipe/agent/skill versions
input assets/artifacts
compiler version
git sha
constraints
```

缺失关键 provenance 时 status不能成为 fully traceable；记录 completeness score/status。

## 9. Approval Integration

Version `APPROVED` 后 immutable；后续 edit 创建新 DRAFT。Approval 记录 exact version id，不能指 Artifact floating head。

## 10. File Attach

文件先 storage verified，后 attach。DB metadata与Object Storage checksum一致；禁止 attach不存在 object。

## 11. Duplicate

相同 content hash 可复用 storage blob，但租户/rights metadata仍独立。跨 tenant 不因hash自动共享可访问 URL。

## 12. GC

两阶段：

```text
mark unreferenced
→ retention delay
→ recheck graph/legal hold
→ delete object
→ record audit
```

Versions本身按产品 retention，不能为了省存储立即抹历史。

## 13. APIs

```text
GET /artifacts/{id}
GET /artifacts/{id}/versions
GET /artifact-versions/{id}
GET /artifact-versions/{id}/lineage
POST /artifact-versions/{id}/fork
POST /artifact-versions/{id}/restore
POST /artifact-versions/{id}/approve
GET /artifact-versions/{a}/compare/{b}
```

## 14. Tests

- concurrent branch head；
- restore；
- fork；
- multi-parent lineage；
- approved immutability；
- cross-tenant hash reuse isolation；
- missing storage object；
- GC live ref保护。

## 15. 验收标准

- [ ] 全部成果可形成 ArtifactVersion。
- [ ] Version immutable。
- [ ] fork/restore/compare可用。
- [ ] lineage/provenance可查询。
- [ ] approved version不覆盖。
- [ ] GC安全。

## 16. Definition of Done

```text
artifact engine implemented
+ version concurrency tests green
+ provenance/GC tests green
```

下一节点：NODE-43 Brand Rules Engine。

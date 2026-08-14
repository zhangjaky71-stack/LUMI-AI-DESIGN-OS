# NODE-45 — Asset Intelligence

> Phase: 5 Design Intelligence  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P1 with P0 essentials  
> Depends on: NODE-18, NODE-23, NODE-36  
> Integrates with: NODE-44 Identity Engine  
> Produces: 资产语义索引、OCR/描述/对象、相似/重复检索、智能 Asset Resolver

---

## 1. 目标

项目拥有数百/数千素材后，Agent不能靠文件名找图。Asset Intelligence给每个已验证 `READY` 资产建立可检索语义、技术 metadata、OCR/region、视觉 embedding、duplicate fingerprint 和版本化派生分析，同时在任何 scoring 之前执行 tenant/permission/rights scope。

NODE-45 不接管 NODE-18 的 binary storage，不接管 NODE-44 的 identity PASS/FAIL，也不硬编码 OCR/VLM/embedding provider。

## 2. Frozen Runtime Principles

1. `READY` asset 才能进入分析。
2. 分析是异步 job，不阻塞上传完成。
3. `organization_id + asset_id + asset_version + index_id` 进入幂等分析身份。
4. metadata 按字段保存 source/confidence；AUTO 不能覆盖 USER。
5. SYSTEM 技术字段不允许被用户/模型伪造覆盖。
6. OCR 保存 bbox/confidence/language。
7. query/search 在候选召回前 tenant/permission/rights filter。
8. embedding model/version/dimension/space 必须匹配 active index。
9. reindex 使用 build → compare → audited switch，不混新旧 embedding space。
10. exact / perceptual-near / semantic-similar 永远是三层不同证据。
11. semantic similarity 不能自动删除素材。
12. selected/approved/rejected 只是 ranking features，不代表训练授权。
13. commercial-use 和 training authorization 独立建模。
14. Agent Resolver 返回候选与解释，Agent 必须选择/确认。
15. 删除资产后先立即从检索隐藏，再异步 reconciliation 清理派生索引。
16. NODE-45 不创建 face-specific persistent/cross-tenant biometric index。

## 3. Ingestion

Asset READY 后：

```text
asset.ready
→ deterministic AnalysisJob
→ NODE-23 analyzer bundle snapshot
→ technical metadata
→ OCR if applicable
→ visual description/tags
→ object/region detection as needed
→ multimodal embedding
→ perceptual hash
→ field-level metadata merge
→ versioned analysis record READY
```

实现：

- `services/asset-intelligence/src/lumi_asset_intelligence/events.py`
- `services/asset-intelligence/src/lumi_asset_intelligence/ingestion.py`
- `services/asset-intelligence/src/lumi_asset_intelligence/analyzers.py`
- `services/asset-intelligence/src/lumi_asset_intelligence/metadata.py`

## 4. Core Contracts

实现于 `model.py`：

```text
VerifiedReadyAsset
AccessScope
MetadataField
OcrBlock
AssetRegion
AnalyzerModelSnapshot
AnalyzerBundleSnapshot
AssetIndexVersion
AssetAnalysisRecord
DuplicateEvidence
AssetSearchRequest / Filters / Hit
UsageSignal
AssetResolverCandidate
```

`CapabilityRegistryPort` 是 NODE-23 控制面边界；`AssetAnalyzer` 是真实 OCR/VLM/object/embedding adapter 的 provider-neutral port。

## 5. Metadata

保存：

```text
media type
size/dimensions/duration
alpha/color space
OCR text
language
visual tags
objects/regions
semantic description
embedding model/version
per-field source/confidence
```

优先级：

```text
protected technical field: SYSTEM authoritative
semantic/user-editable field: USER > SYSTEM > AUTO
```

自动标签不能覆盖用户手工标签/字段。

## 6. OCR

用于 Logo/包装文字、海报文字、scanned asset 等。`OcrBlock` 保存：

```text
text
language
confidence
bbox
analyzer id/version
```

OCR 权限继承 source asset；查询不允许越过 `AccessScope`。

## 7. Embeddings

P0 runtime 通过 NODE-23 注册的 multimodal embedding capability snapshot 接入。保存并校验：

```text
embedding_model_id
embedding_model_version
preprocessor/analyzer provenance
embedding_dimensions
embedding_space_id
index_version
```

query embedding 必须与 active index model/version/dimension 一致，否则 fail closed。

## 8. Duplicate / Similarity

实现：`duplicates.py`

```text
EXACT                         SHA-256 identical
PERCEPTUAL_NEAR_DUPLICATE     versioned pHash policy / Hamming distance
SEMANTIC_SIMILAR              multimodal embedding similarity
```

数据库 `asset_intelligence_duplicate_edges.auto_delete` 被 CHECK 固定为 `false`，杜绝“语义相似=自动删除”。

## 9. Search

实现：`search.py`, `repository.py`, `query_embedding.py`

支持：

```text
TEXT
OCR
SEMANTIC
SIMILAR_TO
HYBRID
```

过滤：

```text
organization
project
brand
permission tags
media type
tags
rights
commercial-use policy
date
approved-only ranking filter
```

关键安全顺序：

```text
scope/filter candidate retrieval
→ lexical/OCR/vector scoring
→ usage ranking feature
→ deterministic final ordering
```

禁止：

```text
GLOBAL VECTOR TOP-K
→ application-layer tenant filter
```

PostgreSQL migration 还提供 `asset_intelligence_semantic_candidates(...)` scope-first pgvector primitive。

## 10. Asset Resolver for Agent

实现：`resolver.py`

输入示例：

```text
"之前用户批准的黑色咖啡杯产品图"
```

返回：

```text
asset id/version
preview ref
why matched
source ref
rights/commercial use
approval state
similarity
requires_agent_confirmation=true
```

Agent 必须选择/确认，不靠文件名猜。

## 11. Approved Usage Signals

`SELECTED / APPROVED / REJECTED` 进入有界 ranking feature。

`training_authorization_granted` 独立字段，默认 `false`；选中/批准不会自动变成训练授权。

## 12. Rights Filter

普通搜索可以返回 `UNKNOWN` rights 并附风险解释；商业输出使用 `commercial_search_request()`：

```text
rights ∈ USER_OWNED | LICENSED
AND commercial_use_allowed = true
```

是否可训练与是否可商业使用仍是不同字段。

## 13. Privacy / Deletion

实现：`deletion.py` + DB tombstones。

```text
source asset delete
→ analysis state DELETING / retrieval invisible immediately
→ async index reconciliation
→ remove analysis + ranking signals
→ tombstone reconciled
```

OCR/description/embedding retention 不得超过 source asset access/retention。

## 14. Reindex

实现：`index_catalog.py`

```text
BUILDING
→ backfill
→ READY
→ coverage / embedding-space comparison
→ audited promotion decision
→ ACTIVE
→ previous ACTIVE RETIRED
```

每 organization 只允许一个 active index（DB partial unique index）。

## 15. NODE-44 Boundary

`identity_adapter.py` 只输出版本化证据：

```text
asset/index version
checksum
OCR blocks
regions
embedding
embedding model/version
preprocessor version
```

不输出 identity score、threshold 或 PASS/FAIL；校准和身份判定仍属于 NODE-44。

## 16. Persistence

Migration: `db/migrations/0004_asset_intelligence.sql`

新增：

```text
asset_intelligence_index_versions
asset_intelligence_analysis_jobs
asset_intelligence_analysis_records
asset_intelligence_metadata_fields
asset_intelligence_ocr_blocks
asset_intelligence_regions
asset_intelligence_embeddings
asset_intelligence_duplicate_edges
asset_intelligence_usage_signals
asset_intelligence_delete_tombstones
asset_intelligence_semantic_candidates(...)
```

P0 pgvector extension 与 embedding dimension/space provenance 已建模。

## 17. Tests / Fixtures

共享 fixture：

`fixtures/asset-intelligence/node-45-conformance.json`

覆盖：

- exact duplicate；
- perceptual near duplicate；
- semantic-similar non-duplicate；
- OCR + bbox；
- USER metadata precedence；
- rights/commercial filter；
- tenant leak bait；
- permission-restricted asset；
- deletion propagation；
- reindex switch；
- model/version/dimension mismatch；
- Asset Resolver explanation；
- usage signal != training authorization；
- NODE-44 evidence boundary。

测试：`services/asset-intelligence/tests/test_asset_intelligence.py`

## 18. Static Validation / Benchmark

```text
scripts/validate_asset_intelligence.py
scripts/benchmark_asset_intelligence.py
```

Benchmark 只衡量 dependency-free scoped ranking core，报告 median/p95/max；不把远程 OCR/VLM/embedding、PostgreSQL/pgvector、网络/storage 延迟伪装成本节点性能。

## 19. Dedicated CI

`.github/workflows/asset-intelligence.yml`

```text
asset-intelligence-contract
→ asset-intelligence-quality
→ asset-intelligence-integration
→ asset-intelligence-benchmark
```

Integration 启动 `pgvector/pgvector:pg17` 空库并实际应用 `0004_asset_intelligence.sql`。

## 20. 验收标准

- [x] Asset 可按语义/OCR 查询（runtime contract + conformance）。
- [x] duplicate 三级区分。
- [x] Agent resolver 返回解释/rights。
- [x] tenant/permission/rights filter 在 scoring 前。
- [x] embedding/analyzer/index 版本化。
- [x] user metadata 优先自动 metadata。
- [x] deletion/reconciliation contract。
- [x] PostgreSQL/pgvector schema + scope-first function。
- [ ] Hosted contract/quality/integration/benchmark 实际执行 green。
- [ ] 真实 production OCR/VLM/embedding 质量 dataset 完成 provider-specific 评测（不使用 synthetic fixture 冒充）。

## 21. Definition of Done

Engineering implementation is committed. Final completion remains gated on hosted CI actually executing green:

```text
asset indexing/search implemented
+ semantic/OCR fixtures executed green
+ tenant/rights tests executed green
+ pgvector migration executed green
+ benchmark executed
```

当前：**IMPLEMENTED / VALIDATING / not COMPLETE**。

下一节点：NODE-46 Image Generation。

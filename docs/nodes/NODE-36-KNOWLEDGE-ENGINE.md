# NODE-36 — Knowledge Engine

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0/P1 boundary, P0 basic  
> Depends on: NODE-18, NODE-34, NODE-35, NODE-23  
> Produces: 文档/网页/品牌资料 ingestion、chunk、embedding、hybrid retrieval、citation refs

---

## 1. 目标

让 Agent 从用户资料、品牌文档、产品说明、研究结果和项目文件中查事实，并能指出来源。Knowledge 与 Memory 分离：Knowledge 是可检索 source corpus。

## 2. Sources P0

```text
uploaded PDF/text/docs extracted content
web research snapshots/references
brand guide
product information
project notes
approved research reports
```

图片/视频语义到 Asset Intelligence NODE-45 深化。

## 3. Ingestion State

```text
PENDING
EXTRACTING
CHUNKING
EMBEDDING
READY
FAILED
STALE
```

原文件仍由 Asset Storage 管，Knowledge 保存 source ref。

## 4. Document Record

```text
knowledge_document_id
organization_id
project_id?/brand_id?
source_type
asset_id/url_ref
content_hash
parser_version
language
created_at
source_updated_at?
permission_scope
```

## 5. Chunk

```text
chunk_id
document_id
ordinal
text
structured_metadata
page/section
content_hash
token_count
embedding
```

Chunk 不能破坏来源定位；PDF 保留 page/section。

## 6. Parsing

优先 native text extraction；OCR 仅扫描件/无文本时 fallback。表格/结构化内容尽量保留结构，不全压成无意义段落。

## 7. Chunking

按文档结构（heading/page/semantic boundary）优先；固定 token window 作为 fallback。配置版本化并纳入 content hash/ingestion version。

## 8. Hybrid Retrieval

```text
query
→ permission/scope filter
→ keyword/full-text
+ vector search
→ fusion
→ rerank
→ diversity/dedupe
→ context spans + citations
```

P0 可 PostgreSQL full-text + pgvector；规模瓶颈后再拆专用 search/vector。

## 9. Query Expansion

允许 model 生成检索 query，但必须保留 original query；生成 query 不作为事实。

## 10. Citations

Retrieval result：

```text
text span
source document id
page/section
asset/url reference
relevance
```

Agent 对事实型研究产出应引用 source refs；不能用 memory 当外部事实来源而不标注。

## 11. Freshness

Web/source 有 `source_updated_at/observed_at`；外部事实有 stale policy。时间敏感研究 Recipe 要求最新检索，不盲用旧知识。

## 12. Permissions

Chunk 继承 source access。查询在 vector search 前就 tenant/filter，禁止先全局召回后在应用层过滤泄漏相似文本。

## 13. Prompt Injection

外部文档内容 trust=UNTRUSTED_DATA；检索器返回 data，不允许其中 instruction 改写 Agent system policy。

## 14. Re-index

parser/embedding model 变更：新 index version + backfill，切换后旧 index 可回滚。不要原地混合不同 embedding space。

## 15. Tests

- PDF page citation；
- tenant permission；
- stale source；
- malicious instruction retrieval；
- hybrid beats vector-only fixture；
- reindex version；
- deletion propagates to index。

## 16. 验收标准

- [ ] 上传文档可 ingestion/retrieve。
- [ ] hybrid retrieval。
- [ ] citation page/section 可回查。
- [ ] tenant filter 在 retrieval 层。
- [ ] external content 不能 prompt inject。
- [ ] embedding/parser version 可重建。

## 17. Definition of Done

```text
ingestion + hybrid search implemented
+ citation fixtures green
+ permission/injection tests green
```

下一节点：NODE-37 Agent Team。

# NODE-45 — Asset Intelligence

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P1 with P0 essentials  
> Depends on: NODE-18, NODE-23, NODE-36  
> Produces: 资产语义索引、OCR/描述/对象、相似/重复检索、智能 Asset Resolver

---

## 1. 目标

项目拥有数百/数千素材后，Agent不能靠文件名找图。Asset Intelligence给每个资产建立可检索语义、技术metadata、视觉embedding和派生分析，同时保持rights/tenant过滤。

## 2. Ingestion

Asset READY后：

```text
technical metadata
→ OCR if applicable
→ visual description/tags
→ object/region detection as needed
→ embeddings
→ duplicate fingerprint
→ index READY
```

分析任务异步，不阻塞上传完成。

## 3. Metadata

```text
media type
size/dimensions/duration
alpha/color space
OCR text
language
visual tags
objects/regions
primary colors optional
semantic description
embedding model/version
auto vs user metadata
```

自动标签不能覆盖用户手工标签；分字段 source/confidence。

## 4. OCR

用于：

- Logo/包装文字；
- 海报文字；
- scanned assets。

保留 bounding boxes/confidence，敏感文档按 permissions处理。

## 5. Embeddings

P0使用 NODE-23 注册的 multimodal embedding候选；embedding version与模型id保存。模型升级走 reindex。

## 6. Duplicate

分层：

```text
exact checksum
perceptual hash near duplicate
embedding semantic similar
```

不能把“语义相似”自动当重复删掉。

## 7. Search

支持：

```text
text query
filters: type/project/brand/tags/rights/date
similar-to asset
OCR query
semantic query
```

结果在数据库检索前 tenant/permission filter。

## 8. Asset Resolver for Agent

输入：

```text
"之前用户批准的黑色咖啡杯产品图"
```

返回候选：

```text
asset id
preview
why matched
source/rights
approval/use metadata
similarity
```

Agent必须选择/确认，不靠文件名猜。

## 9. Approved Usage Signals

记录用户选中/批准/拒绝作为 ranking features，但不自动用作模型训练授权。

## 10. Rights Filter

Recipe用于商业输出时可过滤 `rights=UNKNOWN` 或提示风险。素材是否可训练与是否可商业使用是两个字段。

## 11. Privacy

OCR/description/embedding遵循 Asset access和retention。删除 asset 后 index异步删除并有 reconciliation。

## 12. Reindex

```text
index_version
embedding_model
analyzer_version
```

新版本后台 build → compare → switch，不混 space。

## 13. Tests

- exact duplicate；
- perceptual duplicate；
- semantic search；
- OCR；
- rights filter；
- tenant leak；
- deleted asset removal；
- reindex switch。

## 14. 验收标准

- [ ] Asset可按语义/OCR查询。
- [ ] duplicate三级区分。
- [ ] Agent resolver返回解释/rights。
- [ ] tenant filter在检索前。
- [ ] embedding/analyzer版本化。
- [ ] user metadata优先自动metadata。

## 15. Definition of Done

```text
asset indexing/search implemented
+ semantic/OCR fixtures green
+ tenant/rights tests green
```

完成 Phase 5，下一节点：NODE-46 Image Generation。

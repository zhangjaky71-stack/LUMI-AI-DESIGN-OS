# Asset Intelligence Runtime V1

## Purpose

NODE-45 turns verified `READY` assets into a tenant-scoped semantic index that Agents can query by meaning, OCR text, visual similarity, metadata and approved usage. Binary upload, malware/MIME/checksum validation and preview generation remain NODE-18 responsibilities.

## Non-negotiable boundaries

1. **No filename guessing.** Search and Agent resolution rank analysis evidence, not user filenames.
2. **Scope before score.** `organization_id`, project/brand scope, permission tags and rights are applied before lexical/OCR/vector scoring.
3. **No mixed embedding spaces.** Every index pins analyzer version, embedding model/version, preprocessor version, registry snapshot, vector dimensions and `embedding_space_id`.
4. **No semantic-equals-duplicate shortcut.** Exact checksum, perceptual near-duplicate and semantic similarity are separate evidence tiers.
5. **No automatic deletion from similarity.** The DB duplicate edge has `auto_delete=false` as a hard check.
6. **Manual metadata wins over automatic metadata.** AUTO analyzers cannot overwrite USER fields; protected technical metadata is SYSTEM-owned.
7. **Commercial rights and training authorization are different fields.** Approval/selection signals affect ranking only.
8. **NODE-44 owns identity decisions.** NODE-45 exports versioned OCR/region/embedding evidence but never computes an identity PASS/FAIL threshold.
9. **No biometric index.** NODE-45 has no face-specific persistent or cross-tenant index.
10. **Deletion propagates.** Tombstoned assets disappear from retrieval before asynchronous physical index reconciliation completes.
11. **Usage is reranking only.** Selected/approved/rejected signals cannot manufacture relevance for an unrelated query.

## READY ingestion

```text
NODE-18 asset.ready
  -> deterministic AnalysisJob (PENDING)
  -> resolve analyzer bundle from NODE-23 registry snapshot
  -> system technical metadata
  -> OCR (when applicable)
  -> visual description/tags
  -> object/region analysis (when applicable)
  -> multimodal embedding
  -> perceptual fingerprint
  -> merge field-level metadata with USER precedence
  -> persist versioned AssetAnalysisRecord
  -> READY in target index version
```

Analysis does not block upload completion. Job identity binds organization, asset id/version, index id and source event id, making retries idempotent.

## Analyzer provider boundary

The core package is deliberately dependency-free. Production model adapters implement `AssetAnalyzer`; NODE-23 supplies the versioned `AnalyzerBundleSnapshot`. The runtime refuses any analyzer/embedding bundle whose model id, model version, preprocessor version, registry snapshot or vector dimensions do not match the target index.

`FixtureAnalyzer` and `StaticCapabilityRegistry` exist only for deterministic conformance tests. They are not production OCR/VLM implementations and are not model-quality evidence.

## Metadata model

Every derived field can carry:

```text
key
value
source = SYSTEM | USER | AUTO
confidence
analyzer_id
analyzer_version
```

Protected technical fields such as checksum/MIME/media type/size/dimensions are SYSTEM-owned. USER metadata outranks AUTO metadata for user-editable semantic fields.

OCR blocks retain text, language, confidence and bounding box. Object/region detections retain label, confidence and bounding box.

## Index versioning / reindex

Each index records:

```text
index_id
version
analyzer_version
embedding_model_id
embedding_model_version
embedding_preprocessor_version
embedding_dimensions
embedding_space_id
registry_snapshot_id
state = BUILDING | READY | ACTIVE | RETIRED | FAILED
```

Upgrade flow:

```text
create BUILDING candidate
-> backfill
-> mark READY
-> compare coverage and embedding-space change
-> explicit audited promotion decision
-> candidate ACTIVE
-> previous ACTIVE RETIRED
```

Search only accepts an ACTIVE index. Historical analysis remains attributable to the index/model/analyzer version that produced it.

## Duplicate and similarity tiers

### EXACT

Same verified SHA-256 checksum. This is binary identity evidence, not necessarily permission to delete an asset record.

### PERCEPTUAL_NEAR_DUPLICATE

Versioned perceptual-hash policy and Hamming distance indicate a visual near-copy such as a compression/crop variant.

### SEMANTIC_SIMILAR

Embedding similarity means content is visually/semantically related. A travel mug and a ceramic cup may be semantic neighbors while being different assets. This tier must never be promoted to an automatic deletion decision.

## Search security boundary

Application runtime calls only:

```text
repository.scoped_candidates(scope, filters, active_index_id)
```

The repository removes unauthorized rows before the search engine calculates any score. The PostgreSQL migration also defines `asset_intelligence_semantic_candidates(...)` with organization, permission tags, rights, project/brand and commercial-use predicates in the candidate query. The SQL path additionally requires the requested index to be `ACTIVE` and requires each embedding row to match the index's model/version/preprocessor/dimension/space provenance before vector ranking.

This avoids the unsafe pattern:

```text
GLOBAL VECTOR TOP-K -> application authorization filter
```

which can leak the existence or similarity of assets from another tenant.

## Search modes

```text
TEXT        metadata / semantic-description / tag lexical match
OCR         OCR block lexical match
SEMANTIC    query embedding against active embedding space
SIMILAR_TO  accessible source asset embedding against scoped candidates
HYBRID      weighted semantic + lexical + OCR + bounded usage signals
```

Each mode requires its own relevance evidence before a result is admitted. Usage signals can only rerank an already relevant result. Semantic text queries require a query embedder whose model/version/preprocessor/registry snapshot/dimension match the active index.

## Agent Asset Resolver

Resolver output contains:

```text
asset_id
asset_version
preview_ref
why_matched[]
rights
commercial_use_allowed
approval_state
similarity
source_ref
requires_agent_confirmation=true
```

The Agent selects or confirms a candidate; the resolver does not silently guess a file.

For commercial output, `commercial_search_request()` narrows rights to `USER_OWNED | LICENSED` and requires `commercial_use_allowed=true`. Normal non-commercial resolution may return `UNKNOWN` rights with an explicit risk explanation.

## Approved usage signals

`SELECTED`, `APPROVED`, and `REJECTED` are bounded ranking features. They cannot make an otherwise unrelated asset become a search result. `training_authorization_granted` is stored independently and defaults false. An approved asset is **not** automatically authorized for model training.

## NODE-44 evidence boundary

`identity_evidence_from_analysis()` exports exact asset/index versions, checksum, OCR blocks, regions, embedding and model/preprocessor snapshot. It does not contain `identity_score`, thresholds or PASS/FAIL. NODE-44 remains the calibrated identity authority.

## Deletion and privacy

`mark_deleted` makes the asset non-retrievable immediately. A reconciliation worker then removes analysis/index state and usage signals and closes the tombstone. OCR/description/embedding retention must never outlive the source asset's access/retention policy.

No face-specific analyzer, biometric template table or persistent biometric search index is defined by NODE-45.

## Production adapters still external to the dependency-free core

- NODE-18 Asset Storage: fetch verified asset/preview binary references.
- NODE-23/Model Gateway: real OCR, VLM description, object detection and multimodal embedding adapters.
- PostgreSQL/pgvector data-access adapter: execute the migration's scoped queries and persistence operations.
- NODE-19 queue/event runtime: consume `asset.ready` and execute AnalysisJob asynchronously.

These are integration boundaries, not duplicated inside the core.

## Conformance fixture

`fixtures/asset-intelligence/node-45-conformance.json` contains synthetic assets for:

- exact checksum duplicate;
- perceptual near duplicate;
- semantically similar but non-duplicate asset;
- OCR poster with bounding box;
- UNKNOWN rights;
- permission-restricted asset;
- cross-tenant similarity bait.

It validates runtime contracts only; it is not a claim about production OCR/embedding quality.

## Performance evidence

`scripts/benchmark_asset_intelligence.py` measures the deterministic in-memory scoped ranking core. It reports median/p95/max and deliberately excludes remote model inference and PostgreSQL/pgvector/network latency. No production latency SLO is invented by this node.

# NODE-45 Acceptance — Asset Intelligence

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-44-identity-engine-release`

## Scope evidence

| Requirement | Evidence | Engineering status |
|---|---|---|
| Consume verified READY assets | `model.py`, `ingestion.py` | Implemented |
| Async `asset.ready` analysis contract | `events.py` | Implemented |
| Idempotent analysis job / record IDs | `events.py`, `ingestion.py` | Implemented |
| Technical metadata | `metadata.py` | Implemented |
| Field-level source/confidence | `MetadataField` | Implemented |
| USER metadata outranks AUTO | `merge_metadata` + tests | Implemented |
| OCR text + bbox + confidence + language | `OcrBlock` + fixture/tests | Implemented |
| Visual description/tags | `AnalyzerOutput` + ingestion | Implemented |
| Object/region contract | `AssetRegion` | Implemented |
| Multimodal embedding contract | analyzer/index contracts | Implemented |
| NODE-23 registry snapshot boundary | `CapabilityRegistryPort` | Implemented |
| Model/version/preprocessor/registry/dimension/space pinned | index + ingestion + query guards | Implemented |
| Exact checksum duplicate | `duplicates.py` | Implemented |
| Perceptual near duplicate | `duplicates.py` | Implemented |
| Semantic similar is distinct | `duplicates.py` + tests | Implemented |
| Similarity cannot auto-delete | DB CHECK `auto_delete=false` | Implemented |
| TEXT / OCR / SEMANTIC / SIMILAR_TO / HYBRID | `search.py` | Implemented |
| Mode-relevant evidence required before usage rerank | `search.py`, static validator | Implemented |
| Tenant/permission/rights before scoring | repository + scoped SQL + tests | Implemented |
| SQL requires ACTIVE index and matching embedding space | `0004_asset_intelligence.sql` | Implemented |
| Commercial-use rights filter | `commercial_search_request` + test | Implemented |
| Agent Asset Resolver explanation | `resolver.py` | Implemented |
| Agent must confirm/select | `requires_agent_confirmation=true` | Implemented |
| Approved usage ranking signals | service/search + test | Implemented |
| Usage != training authorization | separate fields + DB + test | Implemented |
| Reindex build/compare/audited switch | `index_catalog.py` | Implemented |
| No mixed embedding space | index/query/ingestion/SQL guards | Implemented |
| Deleted asset hidden immediately | repository deletion state + test | Implemented |
| Async deletion reconciliation | `deletion.py`, tombstone table | Implemented |
| NODE-44 versioned evidence adapter | `identity_adapter.py` | Implemented |
| No Identity PASS/FAIL in NODE-45 | adapter contract + test | Implemented |
| No biometric index | runtime/schema static gate | Implemented |
| PostgreSQL/pgvector persistence | `0004_asset_intelligence.sql` | Implemented |
| Shared conformance fixture | `node-45-conformance.json` | Implemented |
| Python conformance tests | `test_asset_intelligence.py` | Implemented; hosted execution pending |
| Static architecture validator | `validate_asset_intelligence.py` | Implemented; hosted execution pending |
| Deterministic ranking benchmark | `benchmark_asset_intelligence.py` | Implemented; hosted measurement pending |
| Runtime documentation | `ASSET-INTELLIGENCE-V1.md` | Implemented |
| Dedicated four-stage CI | `.github/workflows/asset-intelligence.yml` | Implemented; hosted execution pending |

## Frozen architecture assertions

1. NODE-18 remains the binary upload/checksum/MIME/malware/preview authority.
2. NODE-23 / Model Gateway owns real model capability registration and provider adapters.
3. NODE-36 remains document/source Knowledge retrieval; NODE-45 owns image/video asset semantics.
4. NODE-44 remains identity scoring/calibration authority; NODE-45 only provides versioned evidence.
5. Search never ranks a global cross-tenant candidate set and filters afterward.
6. Filename is not a semantic ranking feature.
7. Active index pins model, model version, preprocessor, registry snapshot, dimensions and embedding space.
8. Exact checksum, perceptual near-duplicate and semantic similarity remain distinct tiers.
9. Semantic similarity cannot authorize deletion.
10. Usage signals can rerank a relevant candidate but cannot create query relevance.
11. User selection/approval is a ranking signal, not model-training consent.
12. Commercial-use permission and training authorization are separate fields.
13. NODE-45 does not create a persistent/cross-tenant biometric index.

## Conformance cases implemented

- USER metadata survives AUTO metadata;
- repeated ingestion reuses deterministic analysis record;
- exact / perceptual / semantic similarity tiers remain distinct;
- OCR search retains bbox/confidence;
- semantic search excludes cross-tenant leak bait;
- permission-restricted asset excluded/admitted by scope;
- UNKNOWN-rights asset excluded from commercial search;
- approval signal changes ranking but does not grant training authorization;
- Agent resolver returns explanation and confirmation requirement;
- tombstoned asset disappears before physical reconciliation;
- reindex requires READY + comparison + audited switch;
- embedding model/version mismatch rejected;
- NODE-44 evidence contains versions but no identity score;
- AnalysisJob deterministic/idempotent;
- inaccessible SIMILAR_TO source rejected;
- embedding dimension mismatch rejected.

## Fixture honesty

`fixtures/asset-intelligence/node-45-conformance.json` is synthetic. It validates security, versioning, ranking and duplicate contracts. It does **not** demonstrate production OCR recall, VLM caption quality, object detection quality, embedding retrieval quality or real-world search relevance.

Production model-quality evaluation must use approved real assets and the concrete NODE-23 provider/model snapshots selected for deployment.

## Performance honesty

`scripts/benchmark_asset_intelligence.py` benchmarks only the dependency-free in-memory scoped ranking core. It intentionally excludes remote analyzer inference, queue delay, PostgreSQL/pgvector execution and network/storage latency. The node does not invent a production latency SLO where the baseline does not define one.

## Hosted validation

Completion requires these release gates to **actually execute green**:

```text
asset-intelligence-contract
asset-intelligence-quality
asset-intelligence-integration
asset-intelligence-benchmark
```

If GitHub Actions again returns a zero-step `runner_id=0` failure caused by account billing/spending limits, record it as an external CI blocker. Do not mark NODE-45 PASS or COMPLETE.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Next after release evidence: NODE-46 Image Generation.

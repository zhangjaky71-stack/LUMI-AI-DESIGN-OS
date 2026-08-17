# Asset Intelligence Runtime V1

## Purpose

NODE-45 turns a READY NODE-18 Asset into a versioned, searchable intelligence record without making the upload path wait for OCR, vision or embedding work. It is the machine retrieval layer used by agents and by NODE-44 identity signals.

## Boundaries

- **NODE-18 Asset is the fact source.** Storage state, deletion, rights and commercial-use facts are not redefined here.
- **NODE-23 is the model/capability source.** An index pins a published multimodal-embedding claim, model revision, embedding version and dimension.
- **NODE-45 Analysis is derived data.** OCR, tags, regions, descriptions, pHash and vectors can be rebuilt.
- **Index Version is the search-space boundary.** Different embedding/analyzer spaces are never mixed in one query.
- **NODE-44 consumes the active NODE-45 analysis** through a narrow adapter; it does not maintain a second product/logo embedding store.

## Package layout

Pure domain, ingestion, ranking, duplicate and reindex semantics live in `services/asset-intelligence/src/lumi_asset_intelligence`. API-specific PostgreSQL, NODE-18/NODE-23 and NODE-44 adapters live under `apps/api/src/lumi_api/asset_intelligence`.

## Ingestion

`AssetIntelligenceService.schedule_asset_analysis()` returns an idempotency-addressed job and does not run analyzers in the upload request. `analyze_asset()` is the worker-side execution contract. A whole reindex uses the same split: `schedule_index_build()` is non-blocking while `build_index()` is the worker operation.

Analysis requires:

1. same-tenant Asset;
2. Asset status `ready` and not deleted;
3. writable index (`BUILDING`, `READY` or `ACTIVE`);
4. current NODE-23 claim matching the index-pinned model/revision/version/dimensions;
5. analyzer embedding with exactly the pinned dimension.

User metadata has greater precedence than SYSTEM metadata, which has greater precedence than AUTO metadata. AUTO values require analyzer identity/version and confidence.

## Search security order

Candidate retrieval is the security boundary. `scoped_candidates()` applies organization, project, brand, permission tags, rights, commercial-use and explicit filters before lexical/OCR/vector scoring. The PostgreSQL adapter additionally joins current `assets` and `asset_rights` during retrieval, so revoked/deleted assets cannot be authorized by an old analysis snapshot.

Search modes are `TEXT`, `OCR`, `SEMANTIC`, `SIMILAR_TO` and `HYBRID`. Search results contain individual signal scores plus `why_matched` evidence. Agent resolution preserves rights/source/approval signals and always returns `requires_confirmation=true`.

## Duplicate semantics

Three independent tiers are retained:

- `EXACT`: SHA-256 equality;
- `PERCEPTUAL_NEAR_DUPLICATE`: versioned pHash Hamming policy;
- `SEMANTIC_SIMILAR`: same-space embedding similarity.

Semantic similarity is explicitly not an automatic deletion signal.

## Reindex and activation

Each organization has an atomic index version counter. A candidate index builds in isolation, records coverage, becomes READY, is compared to the current active index, then requires an audited promotion decision. Activation is serialized under an organization lock in PostgreSQL and checks the expected prior active index. A stale promotion decision fails instead of overwriting a newer activation.

Only one ACTIVE index per organization is permitted by a partial unique database index.

## Rights and training authorization

Usage feedback (`SELECTED`, `APPROVED`, `REJECTED`) is a ranking feature only. It cannot grant training authorization; service, API and database constraints fail closed on that side channel. Commercial search narrows to currently commercial-use-allowed owned/licensed/public-domain assets.

## Deletion and reconciliation

Delete events first mark matching analysis records `DELETING`, removing them from retrieval immediately. Reconciliation removes derived analysis and usage signals. Durable event/worker scheduling remains a production gate.

## API

Authenticated v1 facade:

- `POST /api/v1/asset-intelligence/indexes`
- `POST /api/v1/asset-intelligence/indexes/{id}/build` (202 job)
- `POST /api/v1/asset-intelligence/indexes/{id}/activate`
- `POST /api/v1/assets/{id}/intelligence/analyze` (202 job)
- `GET /api/v1/assets/{id}/intelligence`
- `POST /api/v1/asset-intelligence/search`
- `POST /api/v1/asset-intelligence/resolve`
- `POST /api/v1/assets/{id}/duplicates`
- `POST /api/v1/assets/{id}/usage-feedback`

Organization scope comes from the existing authenticated organization header/context, not request-body tenant IDs.

## Acceptance boundary

The deterministic local fixtures prove contract behavior for semantic/OCR/text retrieval, duplicate separation, permission and tenant isolation, commercial rights filtering, feedback ranking, reindex switching/CAS, deletion, analyzer drift and NODE-44 consumption. They are not evidence of production OCR/embedding quality or production-scale latency.

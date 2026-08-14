# NODE-36 — Knowledge Engine Acceptance

> Development branch: `node-36-knowledge-engine`  
> Intended stacked base: `node-35-memory-engine-release`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Completion rule: contract, quality and PostgreSQL gates must actually execute green.

## 1. Canonical specification

Source:

```text
docs/nodes/NODE-36-KNOWLEDGE-ENGINE.md
```

NODE-36 implements a searchable source corpus with citations.

It is deliberately separate from NODE-35 Memory Engine.

## 2. Runtime package

```text
apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/
```

Delivered modules:

- `contracts.py`
- `chunking.py`
- `extraction.py`
- `ingestion.py`
- `repository.py`
- `postgres_repository.py`
- `indexer.py`
- `retrieval.py`
- `context_source.py`
- `service.py`
- public `__init__.py`

## 3. Source types

Implemented:

```text
ASSET
URL
TEXT
ARTIFACT
INTERNAL_DOCUMENT
```

Original binary bytes remain owned by Asset Storage.

## 4. Scope model

Implemented:

```text
PROJECT
ORGANIZATION
```

Server-derived durable scope keys:

```text
PROJECT:<project_uuid>
ORGANIZATION
```

Organization-wide write/read requires explicit permissions.

## 5. Cross-project source isolation

`scope_key` is included in:

- deterministic document ID;
- database unique identity;
- advisory-lock key;
- current-version lookup;
- supersede lookup.

A source shared by Project A and Project B therefore creates independent Knowledge indexes.

Regression test:

```text
apps/agent-runtime/tests/test_knowledge_scope_identity.py
```

## 6. Ingestion lifecycle

Implemented state vocabulary:

```text
PENDING
EXTRACTING
CHUNKING
EMBEDDING
READY
FAILED
STALE
SUPERSEDED
DELETED
```

Product ingestion path:

```text
KnowledgeIngestRequest
-> short transaction PENDING/EXTRACTING
-> native extraction outside DB transaction
-> OCR only if native extraction is empty
-> new transaction CHUNKING/EMBEDDING/READY
-> supersede old READY version
```

## 7. Long-running side-effect boundary

Extraction/OCR is intentionally outside PostgreSQL transaction scope.

This prevents a PDF/OCR/model call from holding locks/connections for the duration of external work.

Failures are persisted later using stable codes, not raw exception text.

## 8. Native-first extraction

Implemented:

```text
KnowledgeExtractionPort
KnowledgeExtractionResult
extract_native_then_ocr
```

Native extraction wins when usable text exists.

OCR is a fallback only.

## 9. Structured segments

Implemented source segments with:

```text
text
page
section
metadata
```

Chunk locators preserve page/section and bounded offsets.

## 10. Chunking

Implemented:

- structure-first segmentation;
- token-window fallback;
- bounded overlap;
- deterministic chunk IDs;
- content hashes;
- token estimates;
- citation locators.

## 11. Citation contract

Every result can return:

```text
source type/id/version/hash
document id
chunk id
page/section/offset locator
title
URI
```

This is sufficient for fact-oriented Agent outputs to point to durable source evidence.

## 12. Trust boundary

Implemented Knowledge trust classes:

```text
INTERNAL_DATA
USER_CONTENT
EXTERNAL_UNTRUSTED
MODEL_GENERATED
```

All Knowledge remains data.

`KnowledgeContextSource` always emits:

```text
instruction_authority=none
```

External/user/model content is `UNTRUSTED_RETRIEVED`.

## 13. NODE-34 Context integration

Added:

```text
ContextKind.KNOWLEDGE
```

Knowledge enters:

```text
L4_RETRIEVED
```

with citation and freshness metadata.

## 14. Embedding boundary

Implemented provider-neutral:

```text
KnowledgeEmbeddingPort
```

Knowledge Engine imports no direct model-provider SDK.

Chunk embedding identity includes:

```text
embedding_model
embedding_version
embedding_space_id
embedding_dimensions
```

## 15. Embedding-space isolation

Semantic similarity is disabled unless query and chunk embedding-space IDs match and dimensions are compatible.

Context carrying a generic query embedding but no Knowledge embedding-space ID safely falls back to lexical retrieval.

## 16. Index-version configuration guard

An existing READY identity stores its request hash.

Changing parser/chunker/embedding-space semantics while reusing the same `index_version` produces:

```text
KNOWLEDGE_INDEX_VERSION_CONFIGURATION_CONFLICT
```

No silent mixed index is accepted.

## 17. PostgreSQL full-text retrieval

Migration/ORM include:

```text
search_tsv = generated to_tsvector('simple', text)
GIN index ix_knowledge_chunks_fts
```

The generated column is represented in both Alembic and SQLAlchemy metadata.

## 18. PostgreSQL vector retrieval

Vector candidate query requires:

```text
embedding_space_id match
embedding_dimensions match
```

and orders candidates with pgvector distance.

## 19. ACL before retrieval

Production candidate SQL includes organization/project/organization-scope filtering before either:

- full-text rank;
- vector distance.

The application reranker repeats tenant/project checks as defense in depth.

## 20. Hybrid retrieval

Candidate sources:

```text
PostgreSQL FTS branch
+
PostgreSQL pgvector branch
```

Candidates are deduplicated and reranked with:

```text
semantic
lexical
authority
freshness
```

Then document diversity is applied.

## 21. Query expansion

Original query is always preserved.

Optional expanded queries are bounded retrieval signals only and are never stored as source facts.

## 22. Freshness

Implemented:

```text
observed_at
source_updated_at
require_fresh
max_source_age_seconds
```

A `require_fresh` request without an explicit age window is rejected.

## 23. Stale lifecycle

Governed service supports:

```text
READY -> STALE
```

Only READY documents are retrieval candidates.

## 24. Re-index

New index is built to READY first.

Only then is the prior READY version updated to:

```text
SUPERSEDED
```

A failed rebuild does not destroy the previous ready index.

## 25. Concurrency

Postgres source lock uses:

```text
pg_advisory_xact_lock(hashtextextended(...))
```

with identity:

```text
organization + scope_key + source type + source id
```

Concurrent same-index ingestion converges on one deterministic document ID.

## 26. Optimistic concurrency

Document transitions use version-CAS:

```text
WHERE id = ... AND version = expected
version = version + 1
```

## 27. Deletion

Application deletion is:

```text
READY -> DELETED
```

A deleted document immediately drops out of retrieval because candidate SQL joins only READY documents.

Physical SQL DELETE is revoked from `lumi_app`.

## 28. Persistence

Migration:

```text
0017_knowledge_engine
```

Parent:

```text
0016_memory_engine
```

Tables:

```text
knowledge_documents
knowledge_chunks
```

ORM:

```text
KnowledgeDocumentModel
KnowledgeChunkModel
```

Both models are registered in API metadata.

## 29. Unit tests

Files:

```text
apps/agent-runtime/tests/test_knowledge_engine.py
apps/agent-runtime/tests/test_knowledge_boundaries.py
apps/agent-runtime/tests/test_knowledge_scope_identity.py
apps/agent-runtime/tests/test_knowledge_postgres_contract.py
```

Coverage includes:

- PDF page/section citation;
- tenant/project filtering;
- organization permission;
- prompt injection containment;
- native before OCR;
- OCR fallback;
- stale exclusion;
- reindex supersede;
- delete propagation;
- hybrid vs vector-only false positive;
- embedding-space mismatch;
- idempotent retry;
- same source across projects;
- index configuration drift;
- Context lexical fallback when embedding space is unknown;
- migration/ORM/repository contract.

## 30. PostgreSQL E2E

Script:

```text
scripts/integration_knowledge_engine.py
```

Flow:

1. verify seeded org/project;
2. clear deterministic NODE-36 fixtures with migration role;
3. start two concurrent `KnowledgeIngestRequest` executions;
4. persist PENDING/EXTRACTING before extraction;
5. native extraction produces page/section segments;
6. OCR must not run;
7. finalize CHUNKING/EMBEDDING/READY;
8. require one READY document;
9. search with pgvector + FTS candidate paths;
10. require page 2 / Pricing citation;
11. create source v2;
12. require v1 SUPERSEDED and only v2 READY;
13. search returns only v2;
14. governed delete removes retrieval eligibility;
15. verify vector persisted;
16. prove `lumi_app` physical DELETE raises insufficient privilege;
17. deterministic cleanup.

## 31. Static validator

Script:

```text
scripts/validate_knowledge_engine_contract.py
```

Checks:

- runtime module completeness;
- canonical vocabularies;
- durable ingestion orchestration;
- extraction outside DB transaction;
- native-first OCR policy;
- scope-key tenant isolation;
- index configuration guard;
- provider-neutral embedding;
- ACL-before-score retrieval;
- Context data-only boundary;
- 0017/ORM alignment;
- no direct provider/network/database SDK ambient authority;
- no direct Memory Engine dependency;
- unit/E2E acceptance markers.

## 32. CI contract

Expected workflow:

```text
.github/workflows/knowledge-engine.yml
```

Required jobs:

```text
knowledge-contract
knowledge-quality
knowledge-postgres
```

Hosted job files alone are not a PASS claim.

## 33. Acceptance checklist

- [x] Knowledge/Memory boundary defined.
- [x] Source types implemented.
- [x] Project/organization scope implemented.
- [x] Scope-key tenant isolation implemented.
- [x] Full ingestion lifecycle implemented.
- [x] Native-first extraction and OCR fallback implemented.
- [x] Extraction transaction boundary implemented.
- [x] Structured page/section chunking implemented.
- [x] Citation contract implemented.
- [x] Prompt-injection data boundary implemented.
- [x] ContextKind.KNOWLEDGE implemented.
- [x] Embedding-space isolation implemented.
- [x] Index-version configuration drift guard implemented.
- [x] PostgreSQL FTS candidate retrieval implemented.
- [x] PostgreSQL pgvector candidate retrieval implemented.
- [x] ACL filtering before both candidate branches implemented.
- [x] Hybrid rerank/diversity implemented.
- [x] Freshness/stale policy implemented.
- [x] Reindex/supersede implemented.
- [x] Concurrent same-source convergence implemented.
- [x] CAS implemented.
- [x] Soft delete/retrieval propagation implemented.
- [x] Runtime SQL DELETE revoked.
- [x] 0017 migration implemented.
- [x] ORM metadata implemented.
- [x] Unit/contract tests implemented.
- [x] PostgreSQL integration implemented.
- [x] Runtime documentation implemented.
- [x] Static validator implemented.
- [ ] `knowledge-contract` hosted gate executed green.
- [ ] `knowledge-quality` hosted gate executed green.
- [ ] `knowledge-postgres` hosted gate executed green.

## 34. Current classification

Until all required execution gates actually run green:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

If GitHub returns the known account billing/spending-limit annotation before runner allocation, classification becomes:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

No hosted PASS is claimed without executed steps.

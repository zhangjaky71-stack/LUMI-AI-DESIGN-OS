# Knowledge Engine V1 — NODE-36

Status: `IMPLEMENTED / VALIDATING`

## Purpose

Knowledge is the retrievable source corpus for factual material. It is intentionally separate from
Memory. Memory stores durable user/project decisions and preferences; Knowledge stores source-backed
documents, web snapshots, brand guides, product information, project notes, and approved research.

The hard boundary is:

```text
knowledge content = data
knowledge content != instructions
```

Every Knowledge result entering NODE-34 is `L4_RETRIEVED / KNOWLEDGE /
UNTRUSTED_RETRIEVED` with `InstructionAuthority.NONE`.

## P0 runtime contract

The package `lumi_agent_runtime.knowledge_engine` freezes:

- tenant/project/brand access context;
- six P0 source types;
- structured source sections with optional page and section location;
- immutable document and chunk identities;
- parser/chunker/embedding/index versions;
- source freshness timestamps;
- retrieval permission scopes;
- keyword + vector hybrid ranking;
- pre-score tenant/scope filtering;
- dedupe and per-document diversity;
- page/section/source citations;
- stale inclusion/exclusion policy;
- re-indexing into a new embedding space;
- deletion propagation to retrieval;
- NODE-34 context conversion with zero instruction authority.

## Ingestion pipeline

```text
source adapter
  -> extracted structured sections
  -> authorization
  -> canonical content hash
  -> structure-preserving chunking
  -> embedding
  -> versioned index
  -> READY document
```

NODE-36 deliberately receives extracted sections rather than importing PDF/OCR/provider SDKs inside
the policy core. Binary PDF/DOCX extraction and OCR are runtime adapters. Native extraction must be
preferred; OCR is a fallback only when native text is absent or unusable.

Each section preserves:

```text
text
page?
section?
```

Chunk identity includes the document hash plus page/section/ordinal/text, so citations remain
traceable after retrieval.

## Permission boundary

Filtering is performed by `InMemoryKnowledgeStore.visible_candidates()` before lexical or vector
scoring. Production pgvector/full-text implementations must preserve this order:

```text
tenant + project + brand + permission filter
  -> candidate rows
  -> FTS/vector scoring
  -> fusion/rerank
```

A global vector search followed by application-layer tenant filtering is forbidden.

## Hybrid retrieval

The reference implementation combines lexical overlap and deterministic semantic vectors. The
deterministic embedder is only a dependency-free contract implementation; a production embedding
provider must use the governed model/capability path.

The scoring contract intentionally favors exact identifiers and named terms while retaining semantic
recall:

```text
fusion = 0.62 * lexical + 0.38 * vector
```

Results then apply content-hash dedupe and a per-document diversity cap.

Query expansion is allowed as retrieval input, but `KnowledgeSearchResult.original_query` is
preserved and generated expansions never become facts.

## Citations

Every hit contains a `KnowledgeCitation` with:

```text
document_id
chunk_id
source_ref
title
page?
section?
content_hash
```

NODE-34 context metadata carries the same location fields. Factual research outputs can therefore
render source citations without treating Memory as an external factual source.

## Freshness

A document records `source_updated_at` when known and always records `observed_at`. Search computes
staleness against the configured policy. A stale result is either:

- included with `KNOWLEDGE_STALE_SOURCE_PRESENT`; or
- excluded when the caller requires fresh-only retrieval.

Time-sensitive recipes must request fresh data or trigger source refresh rather than silently using
old web snapshots.

## Re-index safety

Parser, chunker, and embedding versions contribute to `index_version`. Re-index creates a new index
space. Production storage must backfill and switch atomically; mixing embedding vectors from
different spaces in one similarity query is forbidden.

## Deletion

Deletion marks the document deleted and removes its chunks from the reference store. Production
persistence must propagate source deletion to FTS/vector indexes and preserve audit metadata required
by retention policy.

## Production gaps

`reports/nodes/NODE-36/gap-ledger.json` tracks adapters intentionally outside the dependency-free
core:

1. PDF/DOCX native parser + OCR fallback;
2. Postgres full-text + pgvector persistence/migrations;
3. governed production embedding provider;
4. web source refresh scheduler;
5. durable blue/green re-index rollout.

These gaps prevent claims of production persistence/provider completeness, but do not weaken the
frozen authorization, citation, trust, and retrieval contracts.

## Acceptance

NODE-36 is acceptable for contract completion when:

- uploaded/extracted documents ingest and retrieve;
- page/section citations round-trip;
- hybrid retrieval fixtures pass;
- tenant/project/brand filters execute before scoring;
- malicious retrieved instructions retain zero authority;
- stale filtering is deterministic;
- reindex produces a new index version;
- deletion removes content from retrieval;
- hosted Python 3.12 workflow executes tests, Ruff, Pyright, fixtures, and validator.

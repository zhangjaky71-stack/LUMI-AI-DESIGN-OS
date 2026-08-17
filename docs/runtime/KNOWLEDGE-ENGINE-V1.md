# Knowledge Engine V1 — NODE-36

Status: `IMPLEMENTED / VALIDATING / not COMPLETE`

## Purpose

Knowledge is the retrievable, citation-preserving source corpus for factual material. It is
intentionally separate from NODE-35 Memory. Memory stores durable learned preferences, decisions,
and project facts; Knowledge stores evidence-backed documents, web snapshots, brand guides, product
information, project notes, and approved research.

The hard boundary is:

```text
knowledge content = data
knowledge content != instructions
```

Every Knowledge result entering NODE-34 is:

```text
L4_RETRIEVED / KNOWLEDGE / UNTRUSTED_RETRIEVED
InstructionAuthority.NONE
```

## Canonical persistence model

The current `feat/node-*` Agent-stack uses Git-workspace durable persistence rather than the older
experimental Alembic lineage. NODE-36 follows that canonical design through
`GitWorkspaceKnowledgeStore`.

The store contains no Git credentials and performs no network operation. A repository/workspace
owner may commit the resulting canonical JSON files separately.

Layout is scope-partitioned before retrieval:

```text
organizations/<org>/<project-or-org>/<scope>/sources/<source-hash>/
  versions/<knowledge-document-id>.json
  head.json
```

A version manifest contains the immutable document metadata and all citation-preserving chunks for
that index version. The source head selects the active version.

### Atomic activation

A new version is activated in this order:

```text
write + fsync complete version manifest
-> atomic os.replace(version)
-> write + fsync head manifest
-> atomic os.replace(head)
-> update in-process view
```

Therefore a crash before the head move leaves the previous index active; a crash after the head move
cannot expose a half-written chunk set.

## P0 runtime contract

`lumi_agent_runtime.knowledge_engine` freezes:

- tenant/project/brand access context;
- six P0 source classes;
- structured source sections with page/section locations;
- deterministic document/chunk identities;
- parser/chunker/embedding/index versions;
- source freshness timestamps;
- permission scopes;
- lexical + vector hybrid ranking;
- tenant/scope filtering before scoring;
- dedupe and per-document diversity;
- page/section/source citations;
- stale inclusion/exclusion policy;
- immutable reindex history + active source head;
- explicit rollback;
- deletion without implicit old-index resurrection;
- native-first extraction and OCR-only fallback;
- provider-neutral embedding boundary;
- NODE-34 context conversion with zero instruction authority.

## Source ingestion

Binary/source access is outside the policy core. `KnowledgeExtractionPort` is supplied by trusted
Asset/Tool/Sandbox composition and exposes:

```text
extract_native(...)
extract_ocr(...)
```

`KnowledgeIngestionService` executes:

```text
source reference
-> native extraction
-> OCR only if native produced no usable result
-> structured SourceSection[]
-> authorization
-> canonical content hash
-> structure-preserving chunking
-> embedding
-> complete durable index version
-> atomic active-head move
```

The Agent Runtime package imports no PDF filesystem reader, OCR provider SDK, provider key, host
shell, or arbitrary HTTP client. This prevents document ingestion from granting ambient authority to
the Agent runtime.

Each extracted section preserves:

```text
text
page?
section?
```

and chunk identity includes document content, location, ordinal, and text.

## Embedding authority

`KnowledgeEmbeddingPort` is provider-neutral:

```text
version
dimensions
embed(text)
```

The deterministic implementation exists for offline tests and reproducible fixtures only. Production
composition must bind this port through the governed model/capability layer. NODE-36 imports no model
provider SDK or credential.

Different embedding dimensions/spaces are never compared as if compatible. If a caller is using a
different active embedding implementation than a stored index version, semantic contribution fails
closed to `0.0` and lexical retrieval remains available until the requested index is activated.

## Scope-first retrieval

`KnowledgeStore.visible_candidates()` selects only active source heads and enforces:

```text
organization
-> project
-> brand membership
-> permission scope
-> active index head
-> not FAILED/DELETED
```

Only then does `KnowledgeEngine.search()` calculate lexical/vector scores.

A global vector search followed by tenant filtering is forbidden. A future PostgreSQL/search backend
must implement the same `KnowledgeStore` contract and preserve this ordering.

## Hybrid retrieval

Reference scoring is deterministic:

```text
fusion = 0.62 * lexical + 0.38 * vector
```

with content-hash dedupe and per-document diversity. Query expansions may improve recall, but the
original query remains explicit and generated expansions never become facts.

## Citations

Every hit carries:

```text
document_id
chunk_id
source_ref
title
page?
section?
content_hash
```

The NODE-34 Context adapter preserves these fields as metadata and emits a stable `knowledge://`
source ref. Knowledge always has `InstructionAuthority.NONE`, including INTERNAL/brand/user-provided
knowledge.

## Freshness

A source records `observed_at` and optional `source_updated_at`. Search computes deterministic stale
state. Stale evidence may be included with a warning or excluded for fresh-only requests.

Refreshing external web/source snapshots remains the responsibility of research/source orchestration;
Knowledge owns indexing and freshness evaluation, not scheduled crawling.

## Reindex and rollback

Document identity includes:

```text
organization/project/brand/scope
source_ref
content_hash
index_version
```

so a parser/chunker/embedding change produces a distinct immutable version.

Reindex writes the full new version before moving the source head. Historical versions remain
addressable by document ID. `rollback_index()` is explicit and moves the source head only after
authorization.

Replaying an old ingest request is idempotent and **does not** implicitly move the active head back to
that old version.

Deleting the active version tombstones/removes the head and **does not resurrect** the previous
version. Rollback after deletion is an explicit authorized action.

## Restart behavior

`GitWorkspaceKnowledgeStore` reconstructs:

- documents;
- chunks;
- source history;
- active heads;
- deleted-head state

from canonical JSON at startup. It rejects schema mismatch, duplicate document IDs, chunk/document
mismatch, and corrupted head/source identity.

This means Knowledge retrieval and citations survive Agent Runtime restart without relying on process
memory.

## Memory vs Context vs Knowledge

```text
NODE-35 Memory
  durable learned preferences/decisions/facts

NODE-36 Knowledge
  evidence corpus + citation + retrieval index

NODE-34 Context
  per-run/task derived view assembled from selected sources
```

Knowledge never promotes retrieved document text to instructions, and Memory must not masquerade as
an external citation source.

## Remaining adapter/operations boundaries

`reports/nodes/NODE-36/gap-ledger.json` is authoritative.

- Concrete PDF/DOCX/OCR readers remain injected NODE-18/Tool/Sandbox adapters; native→OCR ordering is
  already enforced by NODE-36.
- Production embedding implementation must bind `KnowledgeEmbeddingPort` to the governed model layer.
- Scheduled re-fetch of web snapshots remains research/source-refresh orchestration.
- PostgreSQL FTS/pgvector is now an optional scale backend, not a canonical NODE-36 correctness gate.

## Acceptance

Release-blocking acceptance requires:

- extracted/uploaded source ingestion through the extraction port;
- native-before-OCR and OCR fallback tests;
- page/section citation round-trip;
- hybrid retrieval fixtures;
- tenant/project/brand/scope filter before scoring;
- malicious retrieved instruction with zero authority;
- stale include/exclude behavior;
- durable workspace restart retaining active head and citation;
- reindex retaining old version while activating the new version;
- explicit rollback after restart;
- deleting active head without implicit previous-version resurrection;
- package-level provider/DB/network ambient-authority scan;
- hosted Python 3.12 tests + Ruff + Pyright + static contract.

NODE-36 remains `not COMPLETE` until the required hosted workflow receives a real runner and executes
green.

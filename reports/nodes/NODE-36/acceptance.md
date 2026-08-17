# NODE-36 Acceptance — Knowledge Engine V1

## Status

`IMPLEMENTED / VALIDATING / not COMPLETE`

The current branch contains changes newer than the earlier hosted run. No hosted PASS or current-head
`BLOCKED_EXTERNAL` classification is claimed until the latest head receives its own workflow/job
evidence.

## Delivered

### Knowledge identity and sources

- six P0 knowledge source classes;
- tenant/project/brand/scope-bound access context;
- source refs and source freshness timestamps;
- structured page/section evidence;
- deterministic content/document/chunk identities;
- parser/chunker/embedding/index version identity.

### Ingestion

- `KnowledgeExtractionPort` for trusted Asset/Tool/Sandbox composition;
- native extraction always attempted before OCR;
- OCR accepted only as an explicit fallback result;
- extraction completes before durable Knowledge mutation;
- `KnowledgeIngestionService` converts extracted sections to the indexed corpus;
- no provider SDK, database SDK, host shell, arbitrary HTTP client, or source credential in the
  Knowledge package.

### Durable persistence

- `GitWorkspaceKnowledgeStore` on the canonical `feat/node-*` persistence model;
- immutable complete version manifests;
- fsync + atomic `os.replace` writes;
- active source-head manifest;
- crash-safe ordering: complete version before head activation;
- startup reconstruction and corruption checks;
- retrieval survives process restart;
- deleted active head does not automatically expose the previous index.

### Reindex / rollback

- document identity includes source/content/index version;
- reindex creates a separate historical document identity;
- previous versions remain addressable;
- active source head moves only after the new version is complete;
- replaying an old exact request is idempotent and does not roll the active index backward;
- explicit authorized `rollback_index()`;
- active head survives restart;
- deleting current head does not implicitly resurrect older history.

### Retrieval

- scope/tenant/project/brand filter before scoring;
- only active source heads enter scoring;
- lexical + vector hybrid scoring;
- dimension mismatch fails semantic contribution closed to zero while lexical retrieval remains;
- content-hash dedupe;
- per-document diversity;
- query expansion preserves the original query and does not become evidence;
- stale warning and fresh-only behavior.

### Citations and Context

- document/chunk/source/page/section citation round-trip;
- NODE-34 `ContextKind.KNOWLEDGE`;
- `L4_RETRIEVED`;
- `UNTRUSTED_RETRIEVED`;
- `InstructionAuthority.NONE`;
- knowledge document text cannot alter Agent/system instruction authority.

### Quality assets

- deterministic hybrid benchmark corpus;
- contract/security tests;
- durable restart/extraction/reindex/rollback tests;
- static architecture validator;
- gap ledger distinguishing P0 correctness from external adapters/scale optimizations;
- dedicated Python 3.12 + frozen uv + pytest + Ruff + Pyright workflow.

## Required tests authored

The test suite covers at least:

- PDF-style page/section citation;
- cross-tenant ingest denial;
- cross-project retrieval isolation;
- permission prefilter;
- brand membership;
- malicious retrieved instruction → zero authority;
- exact-identifier hybrid ranking;
- query-expansion provenance;
- stale include/exclude;
- deterministic identity;
- deletion propagation;
- native-before-OCR;
- OCR fallback;
- durable store restart;
- reindex retaining history and moving active head;
- active head surviving restart;
- explicit rollback;
- delete current head without prior-index resurrection.

## Security assertions

- Tenant/project/brand/scope selection occurs before lexical/vector scoring.
- Only active source heads enter retrieval candidates.
- Knowledge content never receives system/agent/user instruction authority.
- Knowledge package imports no provider SDK, SQL/vector DB SDK, subprocess, or broad HTTP client.
- Extraction adapters operate through explicit ports instead of ambient host/source authority.
- Production embedding is represented by a provider-neutral port.
- Old index replay cannot silently alter active source selection.

## Remaining external/composition boundaries

`reports/nodes/NODE-36/gap-ledger.json` is authoritative.

- Concrete PDF/DOCX/OCR source readers remain injected NODE-18/Tool/Sandbox adapters.
- Production embedding composition must bind `KnowledgeEmbeddingPort` to the governed model layer.
- Scheduled external/web refresh belongs to research/source refresh orchestration.
- PostgreSQL FTS/pgvector remains an optional scale backend, not a canonical P0 correctness
  dependency in the current Git-workspace Agent-stack.

## Hosted validation discipline

The previous NODE-36 head had a runner-allocation failure before checkout. That historical result does
not validate this newer head. After the current Draft PR head is observed:

- if a runner executes and a step fails, it is an engineering defect to fix;
- if `steps=[]`, `runner_id=0`, and the GitHub billing/spending annotation is present, classify the
  latest head as `BLOCKED_EXTERNAL`;
- only all required green jobs may move NODE-36 to COMPLETE.

Canonical design: `docs/runtime/KNOWLEDGE-ENGINE-V1.md`

Next node: **NODE-37 — Agent Team**.

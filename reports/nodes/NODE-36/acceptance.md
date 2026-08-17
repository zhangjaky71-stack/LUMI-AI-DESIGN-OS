# NODE-36 Acceptance — Knowledge Engine V1

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE`

Hosted PASS is not claimed. The latest required NODE-36 workflow for head
`9afd24fb664f29822b2fe39577e87c2fc97d92c0` did not receive a runner, so no checkout, compile,
validator, pytest, Ruff, Pyright, or durable test step executed.

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
- source authorization before extractor I/O;
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
- three-stage `knowledge-contract -> knowledge-quality -> knowledge-durable` CI.

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
- unauthorized source rejected before extractor I/O;
- durable store restart;
- reindex retaining history and moving active head;
- active head surviving restart;
- explicit rollback;
- delete current head without prior-index resurrection.

## Security assertions

- Tenant/project/brand/scope selection occurs before lexical/vector scoring.
- Source authorization occurs before extraction/source I/O.
- Only active source heads enter retrieval candidates.
- Knowledge content never receives system/agent/user instruction authority.
- Knowledge package imports no provider SDK, SQL/vector DB SDK, subprocess, or broad HTTP client.
- Extraction adapters operate through explicit ports instead of ambient host/source authority.
- Production embedding is represented by a provider-neutral port.
- Old index replay cannot silently alter active source selection.

## Current hosted Actions evidence

PR: `#103`  
Branch: `feat/node-36-knowledge-engine`  
Head: `9afd24fb664f29822b2fe39577e87c2fc97d92c0`  
Workflow run: `32006525761`  
Required first job: `knowledge-contract` / job `95317031697`

Observed job state:

```text
status=completed
conclusion=failure
steps=[]
runner_id=0
runner_name=""
```

GitHub check-run annotation:

> The job was not started because recent account payments have failed or your spending limit needs
> to be increased. Please check the 'Billing & plans' section in your settings

Therefore this run is **BLOCKED_EXTERNAL**, not a code/test failure. `knowledge-quality` and
`knowledge-durable` were skipped because their prerequisite job never started.

## Remaining external/composition boundaries

`reports/nodes/NODE-36/gap-ledger.json` is authoritative.

- Concrete PDF/DOCX/OCR source readers remain injected NODE-18/Tool/Sandbox adapters.
- Production embedding composition must bind `KnowledgeEmbeddingPort` to the governed model layer.
- Scheduled external/web refresh belongs to research/source refresh orchestration.
- PostgreSQL FTS/pgvector remains an optional scale backend, not a canonical P0 correctness
  dependency in the current Git-workspace Agent-stack.

## Completion rule

NODE-36 remains `not COMPLETE` until all required latest-head hosted gates execute green on a real
runner. If a future run starts and a test/lint/type step fails, that is an engineering defect and must
be fixed rather than classified external.

Canonical design: `docs/runtime/KNOWLEDGE-ENGINE-V1.md`

Next node: **NODE-37 — Agent Team**.

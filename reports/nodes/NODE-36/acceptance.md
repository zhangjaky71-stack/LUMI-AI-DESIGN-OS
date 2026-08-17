# NODE-36 Acceptance — Knowledge Engine V1

## Status

`IMPLEMENTED -> VALIDATING`

Hosted PASS is not claimed until GitHub allocates a real runner and the NODE-36 workflow executes.
As with preceding nodes, a job that fails before checkout with `steps=[]` is
`BLOCKED_EXTERNAL`, not a code failure.

## Delivered

- six P0 knowledge source types;
- structured extracted-section ingestion with page/section preservation;
- immutable content-addressed Knowledge documents and chunks;
- parser/chunker/embedding/index version contracts;
- tenant/project/brand/scope authorization;
- permission filtering before lexical/vector scoring;
- hybrid lexical + vector retrieval;
- content-hash dedupe and per-document diversity;
- source/page/section citations;
- original-query preservation for query expansion;
- stale source warnings and fresh-only mode;
- reindex into a new embedding/index version;
- deletion propagation to retrieval;
- NODE-34 `KNOWLEDGE` context adapter with `UNTRUSTED_RETRIEVED` trust and zero authority;
- deterministic benchmark fixtures;
- static architecture/contract validator;
- explicit production gap ledger.

## Local isolated verification

The local scratch environment was not a complete repository checkout, so a minimal NODE-34 Context
Engine compatibility stub was used only to import and execute the actual NODE-36 package. It was not
committed and is not a substitute for hosted repository integration.

Current evidence:

- NODE-36 pytest: `13/13 PASS`;
- Python compileall: PASS;
- static validator: `NODE36_KNOWLEDGE_ENGINE_VALIDATION_PASS`;
- retrieval fixtures: `14` parsed;
- production gap ledger: `5` entries parsed;
- source/test 100-character audit: PASS with 0 violations.

Local Ruff/Pyright are not claimed because those tools were not available in the isolated scratch
runtime. They remain mandatory hosted gates.

## Security assertions

- Cross-organization documents never enter candidate scoring.
- Project-scoped documents never cross project boundaries.
- Brand-scoped documents require brand membership.
- Retrieval permission filtering happens before vector/keyword scoring.
- Retrieved content cannot gain SYSTEM/AGENT/USER instruction authority.
- Query expansion is retrieval input only and never evidence by itself.
- Deleted documents cannot remain retrievable.
- Mixed embedding index versions are explicitly visible to the caller.

## Production qualification

NODE-36 freezes the runtime contract but does not claim the following adapters are complete:

- native binary PDF/DOCX parsing and OCR fallback;
- PostgreSQL FTS + pgvector durable store;
- governed production embedding provider;
- scheduled web refresh;
- blue/green durable reindex orchestration.

These are tracked in `reports/nodes/NODE-36/gap-ledger.json` and must be closed before production
knowledge persistence is declared complete.

Canonical design: `docs/runtime/KNOWLEDGE-ENGINE-V1.md`

Next node: **NODE-37 — Agent Team**.

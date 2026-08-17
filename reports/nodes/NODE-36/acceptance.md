# NODE-36 Acceptance — Knowledge Engine V1

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

Hosted PASS is not claimed. The first NODE-36 PR workflow attempt was blocked before checkout and
before any repository test or lint step could execute.

## Delivered

- six P0 knowledge source types;
- structured extracted-section ingestion with page/section preservation;
- immutable content-addressed Knowledge documents and chunks;
- parser/chunker/embedding/index version contracts;
- tenant/project/brand/scope authorization;
- project/brand permission scopes bound to their concrete entities;
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

- NODE-36 pytest: `14/14 PASS`;
- Python compileall: PASS;
- static validator: `NODE36_KNOWLEDGE_ENGINE_VALIDATION_PASS`;
- retrieval fixtures: `14` parsed;
- production gap ledger: `5` entries parsed;
- source/test 100-character audit: PASS with 0 violations.

Local Ruff/Pyright are not claimed because those tools were not available in the isolated scratch
runtime. They remain mandatory hosted gates.

## Hosted Actions evidence

PR #103 first triggered dedicated workflow run `32005584825` at head
`e9f8f78d96435e4549b2aa537669492c0091adb1`.

The `knowledge-engine` job `95314273504` ended with:

```text
status=completed
conclusion=failure
steps=[]
```

No checkout, frozen install, pytest, Ruff, Pyright, benchmark parsing, or validator step ran. This is
therefore classified as `BLOCKED_EXTERNAL`, consistent with the hosted runner-allocation blocker on
the preceding stacked nodes. It must not be represented as a code or test failure.

## Security assertions

- Cross-organization documents never enter candidate scoring.
- Project-scoped documents never cross project boundaries.
- Brand-scoped documents require brand membership and matching brand scope identity.
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

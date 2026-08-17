# NODE-49 — Export Engine — Implementation Status

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `feat/node-49-export-engine`  
> Stacked on: `feat/node-48-video-generation`

The canonical specification remains `NODE-49-EXPORT-ENGINE.md`. This implementation status records the code now delivered against that specification without changing its original requirements text.

## Implemented

- exact approved ArtifactVersion snapshots only;
- no latest/head fallback;
- NODE-42 exact snapshot adapter;
- NODE-11 authorization bridge before export and before download;
- NODE-19 `export.package` durable queue binding;
- deterministic export/runtime/package identities;
- operation-id semantic idempotency;
- ORIGINAL exact-byte checksum path;
- verified same-format PNG/JPEG/MP4/PDF/PPTX path;
- renderer port for real conversion;
- safe deterministic ZIP + `manifest.json`;
- exact ArtifactVersion/source-file/checksum/renderer provenance;
- short-lived 60–3600 second download grant contract;
- signed URL/token excluded from persistence;
- PostgreSQL exact snapshot/output/grant persistence;
- Alembic `20260817_0018` after NODE-48 `20260817_0017`;
- exact-version, permissions, checksum, packaging, renderer and codec tests;
- contract / quality / PostgreSQL / 500-item benchmark workflow.

## Not COMPLETE until

See `reports/nodes/NODE-49/gap-ledger.json`. Remaining P0 production gates are real object-storage/presigner adapters, real format-conversion renderers, authoritative NODE-11 permission binding, NODE-19 crash/replay acceptance and hosted/live infrastructure acceptance.

## Evidence

- Runtime architecture: `docs/runtime/EXPORT-ENGINE-V1.md`
- Acceptance record: `reports/nodes/NODE-49/acceptance.md`
- Gap ledger: `reports/nodes/NODE-49/gap-ledger.json`
- CI: `.github/workflows/node-49-export-engine.yml`

## Next

**NODE-50 — Visual Critic & Design Quality Engine** after NODE-49 implementation validation, while NODE-49 production gaps remain visible and unclosed.

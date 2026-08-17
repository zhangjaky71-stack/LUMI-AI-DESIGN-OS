# NODE-49 Acceptance — Export Engine

## Status

**IMPLEMENTED / VALIDATING / not COMPLETE**

This record separates implementation evidence from hosted/live execution evidence. NODE-49 now has an exact-version export control plane, durable adapters, persistence schema, deterministic package logic and validation gates. It does not claim production object-storage/transcoder or hosted CI acceptance green.

## Implemented scope

- exact `artifact_version_id` required for every export item;
- NODE-42 snapshot adapter uses exact `get_version(id)` and never branch head/latest fallback;
- organization/project/artifact/version identity checks before snapshot acceptance;
- APPROVED-only source policy and rejected-rights fail closed;
- NODE-11 authorization bridge before export and again before download grant;
- immutable exact-version snapshot persisted into the export job;
- deterministic export job id and operation-id semantic conflict rejection;
- NODE-19 `export.package` durable job adapter with deterministic runtime job id;
- ORIGINAL copy-through with exact source size/SHA-256 verification;
- verified same-format PNG/JPEG/MP4/PDF/PPTX path without fake transcoding;
- renderer registry contract for real format conversion;
- task byte ceilings and 500-item maximum;
- safe flat output names with traversal/control-character rejection;
- direct single-file packages;
- deterministic multi-file ZIP packaging with `manifest.json` and package SHA-256;
- exact ArtifactVersion ids, source file ids/checksums and renderer versions in manifest;
- short-lived download grants bounded to 60–3600 seconds;
- grant persistence intentionally excludes URL/token/signature values;
- restart-safe export job/snapshot/output/package codec;
- PostgreSQL persistence for specs/jobs/items/outputs/download-grant audit;
- Alembic revision `20260817_0018` directly after NODE-48 `20260817_0017`;
- exact-version, permission, checksum, ZIP, traversal, renderer and codec tests;
- static architecture validator;
- deterministic 500-item packaging benchmark harness;
- dedicated contract / quality / PostgreSQL / benchmark workflow;
- five-item production gap ledger.

## Deterministic test intentions

The committed suite covers:

1. exact-version lookup and absence of branch-head fallback;
2. non-approved ArtifactVersion rejection;
3. authorization failure before queue side effects;
4. operation idempotency and changed-exact-version conflict;
5. ORIGINAL exact byte-length and SHA-256 verification;
6. single-file manifest exact ArtifactVersion trace;
7. batch ZIP with manifest and whole-package checksum;
8. output filename traversal rejection;
9. download reauthorization and transient signed-URL behavior;
10. grant metadata persistence without URL contents;
11. same-format PNG validation and explicit real-transcoder requirement;
12. restart codec preserving exact version id/version number/source keys/checksums.

These are committed test intentions until an execution environment actually runs them.

## Hosted gates

The NODE-49 workflow requires:

- `export-contract`
- `export-quality`
- `export-db`
- `export-benchmark`

The PostgreSQL job migrates the full schema to Alembic head, checks the five NODE-49 tables and asserts that `export_download_grants` contains neither `url` nor `token` columns.

NODE-48 hosted execution was previously blocked before runner startup by the repository/account GitHub Actions Billing/Spending Limit state. NODE-49 must be judged from its own actual run after PR creation; if the same account blocker appears, it is infrastructure-blocked rather than code-green/code-red evidence.

## Production completion gates

NODE-49 remains **not COMPLETE** until all five gap-ledger items close. In particular, same-format verified delivery is implemented, but conversion renderers may not rename bytes and claim a new format. Real PNG/JPEG conversion, MP4 normalization, PDF export and PPTX/PDF deck rendering require production renderer adapters and binary acceptance fixtures.

Production completion also requires real object-storage reads/writes/presigning, authoritative NODE-11 permission binding and NODE-19 crash/replay acceptance.

## Files

- `services/export-engine/src/lumi_export_engine/*`
- `services/export-engine/tests/*`
- `apps/api/src/lumi_api/export_engine/*`
- `apps/api/src/lumi_api/persistence/models_export_engine.py`
- `apps/api/migrations/versions/20260817_0018_export_engine.py`
- `apps/api/migrations/versions/20260817_0018_sql/*`
- `tools/node49/*`
- `docs/runtime/EXPORT-ENGINE-V1.md`
- `reports/nodes/NODE-49/gap-ledger.json`
- `.github/workflows/node-49-export-engine.yml`

## Next node

After NODE-49 implementation validation, proceed to **NODE-50 — Scheduler Engine** while keeping NODE-49 production gaps visible and unclosed.

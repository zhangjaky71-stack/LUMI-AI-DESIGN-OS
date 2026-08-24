# NODE-22 Release Revalidation — 2026-08-24

Status: **CODE-ADDRESSABLE REVALIDATION IN PROGRESS**

This record binds the NODE-22 Model Gateway release-closure remediation to the hosted verification chain without changing the NODE-73 Final Acceptance verdict.

## Verified remediation one-shot

- Workflow: `Release Model Gateway PostgreSQL JSON Fix`
- Run: `32683212834`
- Source head verified by the run: `1a9c6f5e8dca41ba8722d04ff011c4a5856e2f36`
- Result: `success`
- Verified steps:
  - fail-closed PostgreSQL paid-guard patch application;
  - frozen workspace install;
  - strict Ruff and Pyright verification;
  - JSON object decode boundary assertions;
  - full PostgreSQL acceptance environment preparation, migrations, schema check, and seed;
  - durable paid-invocation PostgreSQL acceptance: PASS;
  - migration downgrade and re-upgrade smoke: PASS;
  - one-shot workflow self-removal and verified bot commit: PASS.

## Remediation semantics

The durable idempotency read boundary now accepts PostgreSQL JSONB values only when they decode to a JSON object and fails closed with the stable `IDEMPOTENCY_RESULT_JSON_INVALID` code for malformed or non-object values.

The failure-state update also binds the shared PostgreSQL status parameter explicitly to `varchar(32)` so asyncpg does not infer incompatible `text` and `character varying` types across assignment and comparison expressions.

## Formal revalidation requirement

The successful one-shot is not, by itself, the final Model Gateway workflow verdict. This report intentionally triggers the normal `Model Gateway` pull-request workflow because `reports/nodes/NODE-22/**` is part of its declared path scope. Full code-addressable PASS requires all normal workflow jobs to pass, including hosted PostgreSQL paid-guard acceptance.

## NODE-73 boundary

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.** This record does not replace the live staging/production/evidence chain required for an auditable final `accepted=true` decision.

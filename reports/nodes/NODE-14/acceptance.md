# NODE-14 Acceptance — Constraint Engine V1

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Source completion

- [x] Structured `lumi.constraint/1.0` model and `lumi.constraint-set/1.0`.
- [x] Frozen HARD / SOFT / ADVISORY semantics.
- [x] Frozen seven-level source precedence and same-level conflict behavior.
- [x] All 24 V1 constraint types have evaluator contracts.
- [x] Deterministic Design Operation preflight with stale-version and missing-target fail-closed behavior.
- [x] Batch wrapper preserves atomicity by validating before Design IR mutation.
- [x] Postflight contract for generative/rendered results using adapter observations.
- [x] QR decode/payload hard requirement and quiet-zone/module-size warnings.
- [x] Protected-region diff threshold contract; no exact-pixel-only requirement.
- [x] Policy-authorized override audit model; `SAFETY_SYSTEM` cannot be bypassed.
- [x] Canonical active-constraint SHA-256 snapshot.
- [x] Conservative explicit-user-lock structuring for QR/logo/product/text/generic targets.
- [x] Four deterministic JSON Schema exports.
- [x] 100-case constraint-following benchmark fixture.
- [x] Architecture validator forbids image/OCR/QR/provider/ORM/agent/runtime SDK coupling.

## Local executable validation

The implementation was exercised in an isolated compatibility harness:

- constraint contract tests: `15 passed`;
- source/test/tool compileall: PASS;
- evaluator registry: `24/24`;
- schema export + JSON parse: `4/4` PASS;
- benchmark rows: `100` validated;
- deterministic validator: `NODE14_CONSTRAINT_ENGINE_VALIDATION_PASS`.

The available fallback runtime is Python 3.13.5 with Pydantic 2.13.4. This is supporting evidence only. Canonical repository execution remains Python 3.12 with the frozen workspace lock.

## Hosted validation required before COMPLETE

NODE-14 is stacked on NODE-13 / PR #79. NODE-13 and upstream NODE-09/10/11/12 remain `VALIDATING` because GitHub-hosted Actions are blocked before runner allocation by the account Billing/spending-limit condition already evidenced in the stacked chain.

Do **not** mark NODE-14 COMPLETE until:

1. GitHub Actions can allocate a runner;
2. `uv sync --all-packages --frozen` succeeds on the NODE-14 workflow;
3. architecture/registry/benchmark validation is green;
4. `apps/api/tests/test_constraint_engine_contract.py` is green;
5. schema export and JSON parse checks are green;
6. Ruff and Pyright are green in canonical Python 3.12 CI;
7. repository CI/security gates are green;
8. stacked dependencies are resolved in merge order.

No real QR/OCR/visual-runtime PASS is claimed in NODE-14. Those measurements belong to later runtime adapters and NODE-39; NODE-14 freezes the deterministic contract they must satisfy.

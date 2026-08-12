# NODE-04 Acceptance Report

> Status: **COMPLETE**  
> Node: **NODE-04 — CI Foundation**  
> Implementation Merge Commit: `bfa746b68e20d4f8c7bdeb0d423f4a322a790d69`  
> Clean Acceptance PR: `#1`  
> Clean CI Run: `31587555221`  
> Clean Secret Scan Run: `31587555264`  
> Deliberate Failure PR: `#2` — **CLOSED / NOT MERGED**  
> Failure CI Run: `31588072018`  
> Failure Secret Scan Run: `31588072036`  
> Validated At: `2026-08-12`  
> Required Checks: `frontend`, `python`, `contracts`, `integration`, `secret-scan`

---

## 1. Result

NODE-04 is accepted as the CI foundation for LUMI AI Design OS.

A clean implementation pull request proved that the repository installs reproducibly, formats/lints/typechecks/tests/builds successfully, validates current repository contracts, starts the NODE-03 local infrastructure, completes its integration smoke tests, and passes the blocking secret scanner without any paid model or cloud provider key.

A separate deliberate-failure pull request was then created solely as an acceptance probe. It injected a lint-clean but failing Python test plus the deterministic LUMI secret-scan sentinel. The Python job passed Ruff and Pyright before failing specifically at `Pytest`, while the independent `secret-scan` job failed on the injected sentinel. The probe PR was closed without merge, so none of the deliberate failure content entered `main`.

## 2. Clean PR evidence

Implementation PR `#1` was merged only after the clean gates passed.

| Gate | Run / Job | Result | Evidence |
|---|---|---|---|
| Change classification | CI `31587555221` / `94084872499` | PASS | PR changes classified; core gates deliberately remained non-path-skipped |
| `frontend` | CI `31587555221` / `94084954410` | PASS | Frozen pnpm install, format, lint, typecheck, unit tests, production build, diagnostic artifact |
| `python` | CI `31587555221` / `94084954510` | PASS | Frozen uv sync, Ruff format/lint, Pyright, pytest, diagnostic artifact |
| `contracts` | CI `31587555221` / `94084954463` | PASS | Frozen pnpm lock verification, `uv lock --check`, scaffold/contract foundation checks |
| `integration` | CI `31587555221` / `94084954515` | PASS | Compose validation, NODE-03 infrastructure startup, real infrastructure smoke, cleanup |
| `secret-scan` | Secret Scan `31587555264` / `94084806599` | PASS | Gitleaks completed cleanly against the repository/PR history |
| Dependency review | Dependency Review `31587555278` / `94084806255` | PASS | Native dependency review action executed successfully |

Clean CI diagnostic artifacts were created and retained for seven days:

- `frontend-ci-logs-31587555221` — artifact `9137791588`.
- `python-ci-logs-31587555221` — artifact `9137771014`.

## 3. Deliberate failure evidence

Failure probe PR `#2` was explicitly marked **DO NOT MERGE** and was closed without merge.

| Gate | Run / Job | Expected result | Observed result |
|---|---|---|---|
| `secret-scan` | Secret Scan `31588072036` / `94086422367` | FAIL | **FAIL** — Gitleaks rejected the deterministic test-secret sentinel |
| `python` | CI `31588072018` / `94086534959` | FAIL | **FAIL** — Ruff format/lint and Pyright passed, then Pytest failed on the deliberate test |
| Failure diagnostics | CI `31588072018` / Python job | artifact retained | PASS — Python diagnostics uploaded despite job failure |
| Probe isolation | PR `#2` | never merge | PASS — PR closed, `merged=false` |

This proves the blocking jobs are capable of rejecting bad code and secret leakage rather than merely reporting green on the happy path.

## 4. Reproducibility and cache evidence

- Node runtime is pinned to major `24` and pnpm to `11.4.0`.
- Python runtime is pinned to `3.12` and uv to `0.11.28`.
- `pnpm install --frozen-lockfile` passed in the clean frontend job.
- `uv sync --all-packages --frozen` passed in the clean Python job.
- `pnpm install --lockfile-only --frozen-lockfile` and `uv lock --check` passed in `contracts`.
- pnpm store and Turborepo cache keys include lock/config hashes.
- uv cache is keyed from `uv.lock` through `setup-uv`.
- Integration uses the local-only NODE-03 stack and requires no AWS, production database, commercial model, or provider API credentials.

## 5. Security posture

The blocking OSS fallback is Gitleaks with repository policy `.gitleaks.toml`. Local-only example environment files are allowlisted by path; production configuration paths are not allowlisted.

GitHub native dependency review is present and passed for the clean PR. Periodic pnpm and Python ecosystem audits are recorded as non-blocking reports because registry vulnerability feeds can be noisy and are not used as the sole PR gate.

CodeQL v4 is scaffolded. The repository is currently private, so the workflow is intentionally skipped unless repository variable `LUMI_ENABLE_CODEQL=1` is set after the repository has the required CodeQL/security-events capability. A skipped unavailable optional capability is not represented as a security PASS.

## 6. Branch protection / ruleset action

The target `main` required-check contract is:

```text
frontend
python
contracts
integration
secret-scan
```

The active GitHub connector does not expose repository branch-protection/ruleset administration. Per the NODE-04 specification, the one-time repository-setting action is therefore documented at:

`docs/ci/BRANCH-PROTECTION.md`

This report does **not** claim that the GitHub repository setting itself was automatically applied.

## 7. Delivered CI foundation

- `.github/workflows/ci.yml`
- `.github/workflows/secret-scan.yml`
- `.github/workflows/dependency-review.yml`
- `.github/workflows/codeql.yml`
- `.gitleaks.toml`
- `scripts/ci-contracts`
- `make ci-contracts`
- `make ci-local`
- PR/push concurrency with superseded-run cancellation
- lockfile-bound dependency caches
- frontend/Python failure diagnostics artifacts
- integration diagnostics on failure
- stable required-check names
- NODE-02/NODE-03 acceptance workflows retained as manual regression workflows
- branch-protection setup runbook

## 8. Acceptance criteria

- [x] Push/PR automatically runs the CI foundation workflows.
- [x] TypeScript/frontend format, lint, typecheck, tests, and build pass on clean code.
- [x] Python format, lint, typecheck, and tests pass on clean code.
- [x] Integration infrastructure starts and its smoke tests pass.
- [x] Frozen pnpm and uv installs/locks are reproducible.
- [x] Secret scanner passes clean code and rejects the deterministic injected sentinel.
- [x] CI does not depend on paid model/provider keys.
- [x] A deliberate failing Python test turns the blocking `python` job red at Pytest.
- [x] Failure diagnostics are uploaded as Actions artifacts.
- [x] The deliberate failure PR was closed without merge.
- [x] Required branch-check names and the one-time repository-setting action are documented.

## 9. Definition of Done

```text
CI workflows committed                 PASS
clean PR simulation green              PASS
failure simulation red                 PASS
lockfile reproducibility proven        PASS
secret scanner clean + reject proven   PASS
failure artifacts proven               PASS
probe PR not merged                     PASS
```

**NODE-04: COMPLETE**

Next engineering node: **NODE-05 — Benchmark Harness**.

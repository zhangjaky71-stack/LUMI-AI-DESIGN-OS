# NODE-05 Acceptance Report

> Status: **COMPLETE**  
> Node: **NODE-05 — Benchmark Harness**  
> Implementation PR: `#3` — MERGED  
> Implementation Merge Commit: `573a0d82e4f9deaed5252be1e943a5954b71355a`  
> Clean CI Run: `31591585790`  
> Clean Secret Scan Run: `31591585757`  
> Dependency Review Run: `31591585733`  
> Benchmark Artifact: `eval-smoke-reports-31591585790` / `9139339839`  
> Validated At: `2026-08-12`  
> Required New Check: `eval-smoke`

---

## 1. Result

NODE-05 is accepted as the Benchmark Harness foundation for LUMI AI Design OS.

The implementation establishes a repository-owned, versioned, deterministic evaluation path that can compare a baseline with a candidate before later model, Agent, prompt, and design changes are described as improvements. The mandatory PR smoke path does not require paid model, LangSmith, cloud, or provider credentials.

The clean implementation PR passed every existing NODE-04 gate plus the new blocking `eval-smoke` gate and was merged only after the complete run was green.

## 2. Clean PR evidence

| Gate | Run / Job | Result | Evidence |
|---|---|---|---|
| Change classification | CI `31591585790` / `94097571542` | PASS | Core gates remained non-path-skipped |
| `frontend` | CI `31591585790` / `94097603414` | PASS | Frozen pnpm install, format, lint, typecheck, unit tests, production build |
| `python` | CI `31591585790` / `94097603518` | PASS | Frozen uv sync, Ruff format/lint, Pyright, pytest |
| `contracts` | CI `31591585790` / `94097603459` | PASS | pnpm lock reproducibility, `uv lock --check`, contract foundation checks |
| `integration` | CI `31591585790` / `94097603404` | PASS | NODE-03 infrastructure startup, smoke, cleanup |
| `eval-smoke` | CI `31591585790` / `94097603451` | PASS | Baseline/candidate evaluation, release gate, JSON/Markdown artifact |
| `secret-scan` | Secret Scan `31591585757` / `94097571285` | PASS | Gitleaks clean |
| Dependency review | `31591585733` / `94097570932` | PASS | Native dependency review completed |

CodeQL remained **SKIPPED**, not PASS, because this private repository does not currently enable the optional CodeQL/security-events capability. This does not weaken the required NODE-05 offline benchmark gate.

## 3. Benchmark evidence

Suite: `smoke@1.0.0`  
Cases: **20 versioned deterministic cases**

Final clean comparison from `eval-smoke`:

| Metric | Baseline | Candidate | Gate | Result |
|---|---:|---:|---|---|
| `task_success` | 1.00000 | 1.00000 | candidate >= baseline | PASS |
| `constraint_violation_count` | 0 | 0 | candidate <= baseline | PASS |
| `critical_safety_failures` | 0 | 0 | candidate <= 0 | PASS |
| `cost_usd` P95 | 0.00119 | 0.00109 | candidate <= baseline × 1.2 | PASS |
| `latency_ms` P95 | 119 | 114 | candidate <= baseline × 1.2 | PASS |

Final run IDs:

```text
baseline  = 40aea59911dd9d859b08
candidate = 49b94c6056f155d8195f
```

Overall release gate: **PASS**.

## 4. Report artifact evidence

The clean CI run produced:

```text
Artifact name: eval-smoke-reports-31591585790
Artifact ID:   9139339839
Retention:     14 days
Files:         4
SHA256:        b0c1ea29fb149637780590051d8179e55d847f51bd6fb4a0a01687c4317d45d1
```

The artifact contains baseline and candidate JSON reports plus Markdown output. Equivalent inputs use canonical JSON and deterministic run identity generation.

Python CI also retained diagnostic artifact `python-ci-logs-31591585790` / `9139343361`.

## 5. Harness self-test evidence

The repository Python suite completed **17 tests PASS**, including **10 NODE-05 harness self-tests**. The harness tests prove:

- invalid case schemas are rejected;
- grader exceptions propagate instead of silently becoming zero;
- baseline/candidate suite mismatch is rejected;
- P95 cost aggregation is deterministic;
- report rendering is reproducible;
- live eval disabled or missing a key is explicitly `SKIPPED`;
- a clean smoke candidate passes the release gate;
- an intentionally degraded primary metric fails the release gate.

Pyright completed with `0 errors, 0 warnings, 0 informations` and Ruff format/lint completed successfully.

## 6. Live evaluation safety

NODE-05 does not call paid providers from normal PR CI. Live evaluation requires all of:

```text
LUMI_LIVE_EVAL_ENABLED=1
LUMI_LIVE_EVAL_API_KEY=<secret>
LUMI_LIVE_EVAL_BUDGET_USD=<positive number>
```

If enablement, key, or budget is missing, the live preflight returns **SKIPPED**, never PASS. Provider-specific live adapters are intentionally deferred to later model/provider benchmark nodes.

## 7. LangSmith linkage

Candidate responses and result records support optional `trace_ids`. This allows later Agent/model evaluations to link to LangSmith traces while preserving LUMI's repository-owned JSON/report record as the portable benchmark evidence. Offline smoke requires no LangSmith credential.

## 8. Branch protection / ruleset action

The target `main` required-check contract is now:

```text
frontend
python
contracts
integration
secret-scan
eval-smoke
```

The active GitHub connector does not expose branch/ruleset administration, so this repository-setting action remains documented in `docs/ci/BRANCH-PROTECTION.md`. The check exists and is proven in Actions; this report does not claim the repository ruleset itself was automatically configured.

## 9. Non-blocking validation notes

During implementation, an intermediate Python job encountered a GitHub-hosted runner TLS/CA checkout failure. The same head SHA passed other jobs, and a job-only rerun successfully checked out and reached the code gates. Subsequent fixes addressed actual Ruff/Pyright/pytest configuration issues without weakening lint or typing policy. The final clean run `31591585790` has no such failure and is the acceptance source of truth.

## 10. Definition of Done

```text
eval framework committed                 PASS
smoke dataset versioned (20 cases)       PASS
runner/grader self-tests green           PASS
baseline comparison works                PASS
release regression rejection tested      PASS
JSON + Markdown reports                  PASS
CI eval-smoke blocking job               PASS
existing CI/security/integration gates   PASS
implementation merged to main            PASS
```

**NODE-05 COMPLETE. Next engineering node: NODE-06 — Lovart Capability Matrix.**

# NODE-07 Acceptance Report

> Status: **VALIDATING**  
> Node: **NODE-07 — Model Provider Matrix**  
> Implementation Branch: `node-07-model-provider-matrix`  
> Registry Version: `1.0.0`  
> Observed At: `2026-08-13`  
> Pricing Snapshot Expires: `2026-09-12`

---

## Required evidence

NODE-07 is not COMPLETE until the implementation PR proves all of the following:

- Five provider files are committed: OpenAI, Google, Anthropic, Black Forest Labs, Runway.
- The source catalog contains only first-party provider URLs.
- Registry v1.0.0 contains exactly 28 model records and 27 route-eligible candidates.
- Lifecycle contract is exactly 23 stable, 4 preview, 1 deprecated for this snapshot.
- Deprecated/legacy/shutdown models cannot be route eligible.
- Required modalities are covered: reasoning, image generation, image edit, video generation, embedding.
- Every active candidate has documented provider pricing and official source references.
- Price snapshot expires within 30 days of observation.
- All 28 models remain `NOT_MEASURED` for quality and latency until live benchmark evidence exists.
- Fifteen task routes are versioned and every route maps to a benchmark group.
- `selected_primary` remains null for every route until benchmark evidence exists.
- Preview-only candidate sets require an explicit stable fallback.
- Live provider benchmark is explicitly `SPECIFIED_NOT_RUN` and SKIPPED without key + positive budget.
- `make model-provider-validate` succeeds.
- The validator is executed by the blocking `contracts` GitHub Actions job.
- The Python suite executes the model-provider contract regression test.
- Existing NODE-04 gates remain green: frontend, python, contracts, integration, secret-scan.
- NODE-05 `eval-smoke` remains green on the same PR.
- NODE-06 product-parity contract remains green in the same `contracts` job.
- Human-readable `docs/models/MODEL-PROVIDER-MATRIX.md` matches the machine-readable contract.

When the validation PR is green, this report will record PR number, CI run/job IDs, registry validator output, Python test count, artifacts, final merge SHA, and any explicitly unmeasured live benchmark gaps.

# NODE-05 Acceptance Report

> Status: **VALIDATING**  
> Node: **NODE-05 — Benchmark Harness**  
> Implementation Branch: `node-05-benchmark-harness`  
> Required New Check: `eval-smoke`

## Required evidence

NODE-05 is not COMPLETE until repository evidence proves all of the following:

- The benchmark package is included in Ruff, Pyright, and pytest quality gates.
- `smoke@1.0.0` contains at least 20 versioned cases.
- Offline evaluation executes without paid provider, LangSmith, or cloud credentials.
- Baseline and candidate are executed through the same runner/grader path.
- The clean candidate passes task-success, constraint, safety, P95 cost, and P95 latency release gates.
- A deliberate degraded candidate is rejected by the release gate in harness self-tests.
- Grader exceptions propagate as errors rather than silently becoming a score of zero.
- Missing live-provider enablement/key/budget is reported as `SKIPPED`, not `PASS`.
- JSON and Markdown reports are produced deterministically for equivalent inputs.
- CI runs the blocking `eval-smoke` job and retains its reports as a GitHub Actions artifact.
- The existing NODE-04 gates remain green on the same implementation PR.

When the validation PR is green, this report will record the PR number, CI run/job IDs, artifact ID, final merge SHA, smoke aggregate scores, and any non-blocking capability notes.

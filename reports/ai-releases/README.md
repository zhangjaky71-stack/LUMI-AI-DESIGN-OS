# AI Release Reports

This directory stores reviewed AI release decision records for model, prompt, agent, skill, recipe, critic, constraint, context, and routing changes.

A production release report is evidence, not a manually authored success claim. It must be generated from `scripts/ai-release-gate.py` with:

- an exact immutable production baseline manifest;
- an exact candidate manifest;
- baseline and candidate reports for every blocking executable suite in `evals/release/policy-v1.json`;
- supplemental evidence whose required entries are all `PASS` with non-empty evidence references.

Fixture reports and contract-test outputs do **not** belong here as production evidence. Human pairwise, shadow, canary, rollback, provider benchmark, security red-team, and product-parity evidence may be stored elsewhere, but the release decision must reference them.

Recommended naming:

```text
reports/ai-releases/YYYY-MM-DD/<candidate-release-id>/decision.json
reports/ai-releases/YYYY-MM-DD/<candidate-release-id>/manifest-candidate.json
reports/ai-releases/YYYY-MM-DD/<candidate-release-id>/manifest-baseline.json
reports/ai-releases/YYYY-MM-DD/<candidate-release-id>/supplemental-evidence.json
```

A failed decision is retained for auditability; do not overwrite it with a later passing attempt.

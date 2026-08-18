# NODE-67 Current Implementation Track

This NODE-67 implementation belongs to the current stacked branch chain:

- base: `feat/node-66-security-hardening` (current-track PR #133)
- head: `feat/node-67-observability`
- status: `CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE`

The repository also contains an older PR numbered #67 from a legacy implementation track. Its branch, implementation details, workflow runs and observability evidence are **not** acceptance evidence for this current stacked implementation.

Do not close, merge, retarget or reuse the legacy PR automatically. Current-track acceptance is governed by:

- `docs/nodes/NODE-67-OBSERVABILITY.md`
- `reports/nodes/NODE-67/implementation.md`
- `reports/nodes/NODE-67/gap-ledger.json`
- `reports/nodes/NODE-67/dashboard-spec.json`
- `reports/nodes/NODE-67/alert-policy.json`
- `reports/nodes/NODE-67/slo-policy.json`
- `.github/workflows/node-67-observability.yml`

No dashboard, alert, SLO, Collector, LangSmith or queue-worker propagation claim is considered complete unless the current-track production adapter and executed evidence exist.

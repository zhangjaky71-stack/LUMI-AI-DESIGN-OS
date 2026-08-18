# NODE-66 Current Implementation Track

This NODE-66 implementation belongs to the current stacked branch chain:

- base: `feat/node-65-audit-governance` (current-track PR #132)
- head: `feat/node-66-security-hardening`
- status: `CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE`

The repository also contains an older open PR numbered #66 from a legacy implementation track. Its branch, implementation details, workflow runs and release evidence are **not** acceptance evidence for this current stacked implementation.

Do not close, merge, retarget or reuse the legacy PR automatically. Current-track acceptance is governed by:

- `docs/nodes/NODE-66-SECURITY-HARDENING.md`
- `docs/security/THREAT-MODEL.md`
- `reports/nodes/NODE-66/implementation.md`
- `reports/nodes/NODE-66/gap-ledger.json`
- `reports/nodes/NODE-66/bola-corpus.json`
- `.github/workflows/node-66-security-hardening.yml`
- `.github/workflows/node-66-security-dast.yml`

No scan, DAST, Sandbox or release-control workflow is considered PASS unless its current-head steps actually execute and retained evidence is available.

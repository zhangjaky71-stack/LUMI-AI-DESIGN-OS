# Staging Acceptance Reports

NODE-71 acceptance evidence is archived by immutable release candidate.

Recommended layout:

```text
reports/staging-acceptance/<rc-sha>/preflight.json
reports/staging-acceptance/<rc-sha>/evidence.json
reports/staging-acceptance/<rc-sha>/decision.json
reports/staging-acceptance/<rc-sha>/decision.md
reports/staging-acceptance/<rc-sha>/attachments-or-references.md
reports/staging-acceptance/evidence/
└─ <sanitized-evidence-artifact>.json
reports/staging-acceptance/<rc-sha>/media-generation-e2e/
├─ evidence.json
├─ validation.json
├─ evidence.sha256
├─ s3-head.json
├─ runtime-identity.json
└─ source-run.json
```

Rules:

- the RC SHA in the evidence must be the exact build/image set under test;
- changing code, container image digest, migration head, Agent/Model routing identity, or security-sensitive config requires a new RC acceptance decision;
- `PASS` is evidence-backed, never handwritten without `actual`, `evidence_ref`, and `owner`;
- every `PASS` scenario/parity `evidence_ref` must also resolve through the top-level `evidence_artifacts` catalog;
- `BLOCKED_EXTERNAL` is retained as a blocker for P0 and must reference the dependency/ticket;
- failed decisions are retained and never overwritten by later retries;
- no passwords, cookies, API keys, provider secrets, private prompts, customer production data, or raw sensitive payloads may be stored here;
- large screenshots/logs/traces may live in workflow artifacts or approved observability systems; repository evidence stores stable references.

## Generic immutable evidence artifact binding

`staging/acceptance/evidence-template.json` contains a fail-closed `evidence_artifacts` catalog. Every `PASS` entry in `scenario_results` and `environment_parity` must use an `evidence_ref` that is present in this catalog.

Each catalog entry binds the logical reference to:

```json
{
  "path": "reports/staging-acceptance/evidence/<artifact>.json",
  "sha256": "<64 lowercase hex>",
  "rc_git_sha": "<exact tested RC SHA>"
}
```

The referenced JSON wrapper must use:

```json
{
  "schema_version": 1,
  "kind": "LUMI_STAGING_EVIDENCE_ARTIFACT_V1",
  "artifact_id": "<exact evidence_ref>",
  "status": "PASS",
  "rc_git_sha": "<exact tested RC SHA>",
  "captured_at": "<non-PENDING timestamp>",
  "producer": {
    "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
    "workflow": "<GitHub Actions workflow name>",
    "workflow_path": ".github/workflows/<producer>.yml",
    "run_id": 123,
    "run_attempt": 1,
    "run_url": "https://github.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/actions/runs/123",
    "head_sha": "<producer workflow head SHA>",
    "head_branch": "<producer workflow branch>"
  },
  "payload": {}
}
```

Canonical validator:

```text
scripts/validate_staging_evidence_artifacts.py
```

The validator rejects missing catalog entries, path escape/symlinks, byte-hash drift, RC swaps, artifact-id swaps, non-PASS wrappers, malformed producer identity, and unsafe logical references. During the canonical `Staging Acceptance Gate`, it additionally uses the acceptance job's scoped `actions:read` token to live-fetch every declared producer run and requires the GitHub run to be `completed/success` with matching repository, workflow name/path, head SHA/branch, run attempt and canonical run URL.

The live producer head SHA is the identity of the collector/freeze workflow itself; it is **not required to equal the tested RC SHA**. The tested product identity is separately and immutably bound by `rc_git_sha` and the NODE-71 runtime-image-set contract.

This generic layer establishes evidence bytes, identity and producer provenance. It does not replace scenario-specific semantic validators. Media generation and Tool Gateway controls still use their stronger dedicated contracts, while DB, browser, performance, resilience and other generic PASS claims can no longer rely on an arbitrary free-form string alone.

The canonical workflow archives the resulting runtime binding report as:

```text
reports/staging-acceptance/runtime/evidence-artifact-binding.json
```

## E2E-03 media-generation evidence

`Collect Staging Media Generation E2E` is an explicit `workflow_dispatch` only workflow. It launches the collector from the exact deployed Staging API task definition, requires that the deployed API container image equals the immutable Staging `API_IMAGE_DIGEST`, creates only a synthetic tenant, traverses the deployed Product API and canonical media job path, validates the durable generated object/artifact/provenance chain, and emits sanitized evidence to the Staging exports bucket.

`Freeze Staging Media Generation E2E` accepts only a successful collector run from the same repository, branch and exact RC SHA. It re-runs the fail-closed validator, recomputes the evidence hash, verifies the S3 metadata and immutable runtime identity, refuses non-identical overwrite, and commits only the RC-scoped `media-generation-e2e/` directory.

The collector's short-lived Bearer token, database credentials, Provider credentials, cookies and raw private prompts are never valid frozen evidence fields. Stage snapshots are canonical-JSON hashed and are rejected if sensitive key names are present.

A production deployment in NODE-72 must reference the exact NODE-71 `decision_id` and RC SHA it consumes.

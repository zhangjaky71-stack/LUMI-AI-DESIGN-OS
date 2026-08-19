# Staging Acceptance Reports

NODE-71 acceptance evidence is archived by immutable release candidate.

Recommended layout:

```text
reports/staging-acceptance/<rc-sha>/preflight.json
reports/staging-acceptance/<rc-sha>/evidence.json
reports/staging-acceptance/<rc-sha>/decision.json
reports/staging-acceptance/<rc-sha>/decision.md
reports/staging-acceptance/<rc-sha>/attachments-or-references.md
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
- `BLOCKED_EXTERNAL` is retained as a blocker for P0 and must reference the dependency/ticket;
- failed decisions are retained and never overwritten by later retries;
- no passwords, cookies, API keys, provider secrets, private prompts, customer production data, or raw sensitive payloads may be stored here;
- large screenshots/logs/traces may live in workflow artifacts or approved observability systems; repository evidence stores stable references.

## E2E-03 media-generation evidence

`Collect Staging Media Generation E2E` is an explicit `workflow_dispatch` only workflow. It launches the collector from the exact deployed Staging API task definition, requires that the deployed API container image equals the immutable Staging `API_IMAGE_DIGEST`, creates only a synthetic tenant, traverses the deployed Product API and canonical media job path, validates the durable generated object/artifact/provenance chain, and emits sanitized evidence to the Staging exports bucket.

`Freeze Staging Media Generation E2E` accepts only a successful collector run from the same repository, branch and exact RC SHA. It re-runs the fail-closed validator, recomputes the evidence hash, verifies the S3 metadata and immutable runtime identity, refuses non-identical overwrite, and commits only the RC-scoped `media-generation-e2e/` directory.

The collector's short-lived Bearer token, database credentials, Provider credentials, cookies and raw private prompts are never valid frozen evidence fields. Stage snapshots are canonical-JSON hashed and are rejected if sensitive key names are present.

A production deployment in NODE-72 must reference the exact NODE-71 `decision_id` and RC SHA it consumes.

# Staging Acceptance Reports

NODE-71 acceptance evidence is archived by immutable release candidate.

Recommended layout:

```text
reports/staging-acceptance/<rc-sha>/preflight.json
reports/staging-acceptance/<rc-sha>/evidence.json
reports/staging-acceptance/<rc-sha>/decision.json
reports/staging-acceptance/<rc-sha>/decision.md
reports/staging-acceptance/<rc-sha>/attachments-or-references.md
```

Rules:

- the RC SHA in the evidence must be the exact build/image set under test;
- changing code, container image digest, migration head, Agent/Model routing identity, or security-sensitive config requires a new RC acceptance decision;
- `PASS` is evidence-backed, never handwritten without `actual`, `evidence_ref`, and `owner`;
- `BLOCKED_EXTERNAL` is retained as a blocker for P0 and must reference the dependency/ticket;
- failed decisions are retained and never overwritten by later retries;
- no passwords, cookies, API keys, provider secrets, private prompts, customer production data, or raw sensitive payloads may be stored here;
- large screenshots/logs/traces may live in workflow artifacts or approved observability systems; repository evidence stores stable references.

A production deployment in NODE-72 must reference the exact NODE-71 `decision_id` and RC SHA it consumes.

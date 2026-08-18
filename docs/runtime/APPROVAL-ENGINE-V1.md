# Approval Engine Runtime V1

## Canonical flow

```text
exact subject
→ approval_requests(PENDING)
→ approval_decisions
→ approval_requests terminal decision
→ approval_effects(PENDING)
→ effect worker
   ├─ ArtifactEngine exact-version approve
   └─ AgentRun formal approval resume
```

The decision is canonical before effects execute. Runtime failures never erase the human decision.

## ArtifactVersion P0

Request snapshot:

```text
artifact_version_id
artifact:vN
content_hash
status=READY
required_permission=artifact.approve
```

Decision rechecks the same exact row and hash. Branch head/latest is intentionally irrelevant: approval never drifts from v3 to v4.

## Browser boundary

Public create accepts only exact ArtifactVersion + title/summary/expiry. Graph bridge IDs are internal-only. Public responses omit interrupt/resume state, effect payload, raw error, provider and storage internals.

## Graph bridge boundary

Internal orchestration may attach:

```text
agent_run_id
task_id
interrupt_id
resume_version
```

On durable decision, an `AGENT_RUN_RESUME` effect may be created. The adapter resumes with:

```json
{
  "kind": "approval",
  "value": {
    "approval_id": "...",
    "decision": "APPROVED|REJECTED|CHANGES_REQUESTED",
    "reason": "...",
    "feedback": {}
  }
}
```

Production graph-node creation, worker composition and restart E2E remain open.

## Governance

- Project access is organization-scoped and project-member scoped.
- Decision additionally requires the Approval's required permission.
- Audit history is immutable and audit API requires `admin.audit.read`.
- Legacy direct Artifact approve is fail-closed for browser callers.
- Reject/changes require feedback.
- Expired subjects never autoapprove.

## Recovery

`PENDING` / `FAILED` effects can be retried. `COMPLETED` is idempotent. `RUNNING` crash lease/reclaim is not yet implemented and remains a P0 runtime gap.

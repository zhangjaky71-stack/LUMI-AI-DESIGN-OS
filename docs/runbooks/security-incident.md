# Runbook — Security Incident Recovery

Owner: Security + Platform  
Priority: STOP SHIP for cross-tenant exposure, usable secret exposure, remote sandbox escape, payment bypass or integrity compromise.

## Trigger

Use for suspected credential/token leakage, tenant-boundary violation, malicious admin/tool activity, sandbox escape, compromised build/dependency, object/database tampering, or unauthorized paid side effect.

## First actions

1. Declare incident commander and security owner.
2. Contain the affected capability/account/route. Prefer narrow containment when it is safe; isolate broadly when blast radius is unknown.
3. Preserve evidence: audit events, immutable logs, traces, DB snapshots, object versions, provider request IDs and build/image digests.
4. Do not destroy the only compromised copy before forensic snapshot/export.
5. Rotate/revoke exposed credentials and sessions from the authoritative secret/identity systems. Do not paste replacement secrets into incident documents.
6. If a sandbox escape is suspected, disable the affected sandbox/tool capability, rotate every credential/network identity reachable from that boundary and preserve the workload image/artifacts for analysis.

## Data integrity / recovery

If unauthorized mutation is suspected:

- Establish the incident start/last-known-good time from audit and storage/database evidence.
- Restore PostgreSQL into an isolated destination using `db-restore.md` when point-in-time recovery is necessary.
- Use object versioning and `object-recovery.md` for altered/deleted assets/artifacts.
- Compare restored/current audit records, tenant graph and critical object checksums.
- Reconcile provider/paid operations; never replay unknown external side effects blindly.
- Queue/Agent restart follows `queue-rebuild.md` and `agent-run-reconciliation.md` only after integrity is established.

## Secret exposure

1. Revoke/rotate the exposed key/token/certificate at the provider/secret manager.
2. Invalidate sessions/API tokens when their signing/encryption/lookup boundary may be affected.
3. Search source history, build artifacts, logs and telemetry for the exposed material using NODE-66 scanners/redaction policy.
4. Reduce credential scope and lifetime before reissue where possible.
5. Add a regression detector/test so the same leak path fails the release gate.

## Supply-chain compromise

- Stop deploying the suspect artifact.
- Identify exact image/package/action digest and first affected build.
- Rebuild from a known-good commit with verified lockfiles and trusted builders.
- Do not merely bump a tag while reusing an untrusted build cache/artifact.
- Review signing/attestation/provenance before redeploy.

## Validation before re-enable

- NODE-66 Critical/High security gates satisfy policy.
- Cross-tenant negative authorization tests pass.
- Restored/current database integrity checks pass.
- Required object checksums/versions pass.
- Secrets/sessions are rotated/revoked as scoped by the incident.
- Sandbox escape corpus or affected capability-specific tests pass.
- No unexplained provider/Cost Ledger side effects remain.
- Audit logging/observability is functioning sufficiently to detect recurrence.

## STOP conditions

Do not restore normal production access while blast radius, tenant impact, credential scope, data integrity or external paid side effects remain unknown.

## Exit criteria

- Containment complete and validated.
- Recovery source/time and data-loss window documented.
- All affected credentials/identities addressed.
- Tenant/object/provider integrity reconciled.
- Root cause, corrective actions and owners recorded.
- Explicit Security/Platform sign-off captured before release unblocks.

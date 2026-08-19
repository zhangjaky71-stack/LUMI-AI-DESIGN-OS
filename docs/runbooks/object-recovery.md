# Runbook — Object Storage Recovery

Owner: Platform / Storage  
Applies to: authoritative `assets` / `exports`, ephemeral `sandbox` artifacts, and any DB row containing bucket/object/checksum references.

## Trigger

Use for accidental object DELETE/overwrite, missing object referenced by PostgreSQL, checksum mismatch, bucket damage, or storage/site recovery.

## Production recovery topology

- `assets` and `exports` are authoritative critical buckets. They are versioned in the primary Region and replicated to dedicated versioned buckets in a different AWS Region.
- Production replication uses SSE-KMS source selection, a distinct destination-region KMS key, replication metrics, and **S3 Replication Time Control (RTC) at 15 minutes**.
- Source delete markers are intentionally **not** replicated. A source-side accidental delete must not automatically erase the independently recoverable destination copy.
- `sandbox` is non-authoritative and short-lived. It is not part of the critical cross-region replica set; after a regional event it is rebuilt/reconciled from canonical Task/Agent/Artifact truth rather than treated as a recovery source.
- NODE-73 Production recovery evidence is valid only when the live drill verifies both `assets` and `exports`: source replication `COMPLETED`, destination status `REPLICA`, exact SHA-256 equality, observed lag no greater than 900 seconds, and exact drill-key cleanup in both Regions.

**Existing-object warning:** normal live replication protects objects written after the rule is active. If cross-region replication is enabled after authoritative data already exists, use S3 Batch Replication (or an equivalent audited backfill), inventory the source/destination sets, and verify checksums before calling the historical corpus protected. A fresh-object RTC drill does not prove old objects were backfilled.

## Preconditions

- Identify exact organization/resource from authorized DB context.
- Identify bucket, object key and expected SHA-256 from `asset_files` / `artifact_files` or the canonical owning record.
- Versioning must be enabled for critical source and recovery buckets.
- Do not hard-delete customer versions while investigating.
- Recovery credentials must be scoped to the necessary bucket/prefix.
- For regional recovery, verify the destination Region, destination KMS key, replication rule, observed lag, and replica checksum rather than assuming Terraform configuration equals runtime state.

## Local destructive-safe drill

```bash
docker compose \
  --profile recovery \
  --env-file infra/compose/.env \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.recovery.yml \
  up -d minio minio-init

docker compose \
  --profile recovery \
  --env-file infra/compose/.env \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.recovery.yml \
  run --rm object-recovery-drill
```

The local drill uses only `_node68-drill/<unique-id>/`, verifies DeleteMarker behavior, rewinds to v1, restores v1 as a new current version, then permanently removes only the drill prefix and its versions. Local MinIO timing is not Production replication evidence.

## Protected Production drill

The `Production DR Rehearsal` workflow uses only deterministic `_node73-drill/<deployment-id>/<run-id>/...` keys. It performs two separate proofs:

1. **Version recovery on canonical `exports`:** write v1, write a deliberately different v2, create a delete marker, recover the exact v1 version by VersionId, verify SHA-256, restore it as a new current version, wait for all three data versions to reach source replication `COMPLETED`, then permanently remove only that drill key from both source and recovery buckets.
2. **Cross-region recovery on `assets` and `exports`:** write one fresh drill object per bucket, observe source `COMPLETED` and destination `REPLICA`, verify destination bytes by SHA-256, require measured lag `<= 900s`, then permanently remove only those drill keys and their versions in both Regions.

A failed drill must not produce a `passed=true` canonical recovery decision. Cleanup is part of the gate, not optional housekeeping.

## Recover one object

1. Stop automatic cleanup/lifecycle actions that could age out needed non-current versions.
2. Record current object/version state before changing anything:

```bash
mc ls --versions ALIAS/BUCKET/PATH
mc stat ALIAS/BUCKET/PATH || true
```

3. Select the exact known-good version using timestamp/checksum/business evidence. Never choose merely because it is the newest historical version.
4. Copy the selected version to an isolated local file or quarantine prefix first:

```bash
mc cp --version-id VERSION_ID ALIAS/BUCKET/PATH /tmp/recovered-object
sha256sum /tmp/recovered-object
```

5. Compare SHA-256, byte size and MIME against PostgreSQL/canonical metadata. For media, rerun the normal validation/malware/parser pipeline before serving it.
6. Restore by copying the verified bytes back to the original logical key. In a versioned bucket this creates a new current version and preserves history:

```bash
mc cp /tmp/recovered-object ALIAS/BUCKET/PATH
```

7. Re-read the current object and verify checksum/size/MIME. Confirm the application can read the owning Asset/Artifact through the normal authorized path.

## Recover after DB PITR

After a DB point-in-time restore, do not assume object storage is at the same time point. Produce two sets:

- DB references whose object/key/version/checksum is missing or different.
- Objects/versions created after the DB recovery point and now orphaned from DB truth.

Recover required historical versions first. Quarantine suspected orphans; do not bulk-delete them during the incident. Delete only after retention/incident review confirms they are not needed for reconciliation or audit.

## Site/region failure

1. Confirm the primary Region incident and fence mutating traffic before selecting a recovery copy.
2. Read the frozen Production recovery decision and live S3 replication state. Do not infer current RPO from the most recent scheduled drill alone.
3. For each required authoritative object, establish the canonical expected key/version/checksum from restored DB/business evidence.
4. Verify the recovery-region object bytes and checksum before promoting or copying them. A healthy bucket endpoint is not integrity evidence.
5. Do not propagate source delete markers into the recovery copy during incident handling. Investigate whether a delete was legitimate before changing destination history.
6. If failover requires a new primary bucket, preserve the old source and recovery histories until reconciliation is closed. Do not create two independent writers without an explicit cutover/fencing decision.
7. Reconcile DB PITR time against object creation/version timestamps and quarantine post-PITR orphans until ownership/audit review completes.

## STOP conditions

- Expected checksum cannot be established.
- Recovery would require permanently deleting customer versions to make progress.
- Object ownership/tenant mapping is ambiguous.
- Malware/parser validation fails.
- KMS/encryption key required to read a version is unavailable.
- Required `assets` / `exports` replication is not `COMPLETED`/`REPLICA`, destination bytes disagree with expected SHA-256, or measured lag exceeds the release recovery envelope.
- Historical objects existed before CRR activation and no audited backfill/inventory proof exists.

## Exit criteria

- Required object is restored as a new current version or explicitly served from a verified recovery copy.
- Checksum/size/MIME and application read path verified.
- Historical versions retained according to policy.
- Any DB/object divergence recorded and reconciled.
- Actual restore time and observed version/replication lag recorded in NODE-68/NODE-73 evidence.
- Recovery evidence is frozen in-repository with path + SHA-256 and consumed by Final Acceptance; an Actions artifact alone is not release evidence.

# Runbook — Object Storage Recovery

Owner: Platform / Storage  
Applies to: assets, exports, sandbox artifacts and any DB row containing bucket/object/checksum references.

## Trigger

Use for accidental object DELETE/overwrite, missing object referenced by PostgreSQL, checksum mismatch, bucket damage, or storage/site recovery.

## Preconditions

- Identify exact organization/resource from authorized DB context.
- Identify bucket, object key and expected SHA-256 from `asset_files` / `artifact_files` or the canonical owning record.
- Versioning must be enabled for critical buckets.
- Do not hard-delete versions while investigating.
- Recovery credentials must be scoped to the necessary bucket/prefix.

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

The drill uses only `_node68-drill/<unique-id>/`, verifies DeleteMarker behavior, rewinds to v1, restores v1 as a new current version, then permanently removes only the drill prefix and its versions.

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

Production NODE-72 must define either cross-region bucket replication or an independently recoverable object backup. Failover requires explicit replication-lag/RPO evidence. A healthy secondary endpoint without verified object versions/checksums is not recovery evidence.

## STOP conditions

- Expected checksum cannot be established.
- Recovery would require permanently deleting versions to make progress.
- Object ownership/tenant mapping is ambiguous.
- Malware/parser validation fails.
- KMS/encryption key required to read a version is unavailable.

## Exit criteria

- Required object is restored as a new current version.
- Checksum/size/MIME and application read path verified.
- Historical versions retained according to policy.
- Any DB/object divergence recorded and reconciled.
- Actual restore time and observed version/replication lag recorded in NODE-68 evidence.

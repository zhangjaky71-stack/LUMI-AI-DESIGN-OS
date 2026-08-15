#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-core-dir> <deployment-id> <output-json>" >&2
  exit 64
}

[[ $# -eq 3 ]] || usage
CORE_DIR="$1"
DEPLOYMENT_ID="$2"
OUTPUT_JSON="$3"
[[ "$DEPLOYMENT_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid deployment id" >&2; exit 64; }
mkdir -p "$(dirname "$OUTPUT_JSON")"

DB_INSTANCE="$(terraform -chdir="$CORE_DIR" output -raw postgres_instance_id)"
BACKUP_RETENTION="$(terraform -chdir="$CORE_DIR" output -raw postgres_backup_retention_days)"
[[ -n "$DB_INSTANCE" ]] || { echo "postgres_instance_id missing" >&2; exit 65; }
[[ "$BACKUP_RETENTION" =~ ^[0-9]+$ && "$BACKUP_RETENTION" -gt 0 ]] || { echo "automated backup retention must be > 0" >&2; exit 65; }

DB_STATUS="$(aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE" --query 'DBInstances[0].DBInstanceStatus' --output text)"
[[ "$DB_STATUS" == "available" ]] || { echo "database is not available: $DB_STATUS" >&2; exit 66; }

SNAPSHOT_ID="$(printf 'lumi-predeploy-%s' "$DEPLOYMENT_ID" | tr '._' '-' | cut -c1-255)"
aws rds create-db-snapshot \
  --db-instance-identifier "$DB_INSTANCE" \
  --db-snapshot-identifier "$SNAPSHOT_ID" >/dev/null
aws rds wait db-snapshot-completed --db-snapshot-identifier "$SNAPSHOT_ID"

SNAPSHOT="$(aws rds describe-db-snapshots --db-snapshot-identifier "$SNAPSHOT_ID" --query 'DBSnapshots[0]')"
STATUS="$(jq -r '.Status' <<<"$SNAPSHOT")"
SNAPSHOT_ARN="$(jq -r '.DBSnapshotArn' <<<"$SNAPSHOT")"
[[ "$STATUS" == "available" ]] || { echo "snapshot did not become available" >&2; exit 67; }

jq -n \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg db_instance "$DB_INSTANCE" \
  --arg snapshot_id "$SNAPSHOT_ID" \
  --arg snapshot_arn "$SNAPSHOT_ARN" \
  --arg status "$STATUS" \
  --argjson backup_retention_days "$BACKUP_RETENTION" \
  '{schema_version:1,deployment_id:$deployment_id,db_instance:$db_instance,snapshot_id:$snapshot_id,snapshot_arn:$snapshot_arn,status:$status,backup_retention_days:$backup_retention_days,passed:($status == "available")}' \
  > "$OUTPUT_JSON"

echo "pre-deployment snapshot ready: $SNAPSHOT_ID"

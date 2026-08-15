#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${POSTGRES_SUPERUSER:?POSTGRES_SUPERUSER is required}"
: "${POSTGRES_SUPERUSER_PASSWORD:?POSTGRES_SUPERUSER_PASSWORD is required}"

backup_root="${LUMI_BASE_BACKUP_DIR:-/backup}"
source_host="${LUMI_POSTGRES_SOURCE_HOST:-postgres}"
source_port="${LUMI_POSTGRES_SOURCE_PORT:-5432}"
staging="$backup_root/.current.next"
current="$backup_root/current"

mkdir -p "$backup_root"
rm -rf "$staging"
mkdir -p "$staging"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[recovery] base backup started at $started_at"

PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" pg_basebackup \
  --host="$source_host" \
  --port="$source_port" \
  --username="$POSTGRES_SUPERUSER" \
  --pgdata="$staging" \
  --format=plain \
  --wal-method=stream \
  --checkpoint=fast \
  --progress

pg_verifybackup "$staging"

rm -rf "$current"
mv "$staging" "$current"
printf '%s\n' "$started_at" > "$backup_root/current.started-at"
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_root/current.completed-at"

echo "[recovery] base backup verified and promoted to $current"

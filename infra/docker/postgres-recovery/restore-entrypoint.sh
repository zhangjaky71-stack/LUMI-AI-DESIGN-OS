#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${LUMI_RECOVERY_ISOLATED:-}" != "1" ]]; then
  echo "refusing restore: LUMI_RECOVERY_ISOLATED=1 is required" >&2
  exit 2
fi

pgdata="${PGDATA:-/var/lib/postgresql/data}"
backup_dir="${LUMI_BASE_BACKUP_DIR:-/backup}/current"
archive_dir="${LUMI_WAL_ARCHIVE_DIR:-/var/lib/postgresql/wal-archive}"
target_name="${LUMI_RECOVERY_TARGET_NAME:-}"

if [[ ! -f "$backup_dir/backup_manifest" ]]; then
  echo "verified base backup manifest not found: $backup_dir/backup_manifest" >&2
  exit 2
fi
if [[ ! -d "$archive_dir" ]]; then
  echo "WAL archive not mounted: $archive_dir" >&2
  exit 2
fi
if [[ -n "$target_name" && ! "$target_name" =~ ^[A-Za-z0-9._:-]{1,128}$ ]]; then
  echo "invalid LUMI_RECOVERY_TARGET_NAME" >&2
  exit 2
fi

pg_verifybackup "$backup_dir"

mkdir -p "$pgdata"
find "$pgdata" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a "$backup_dir"/. "$pgdata"/
rm -f "$pgdata/postmaster.pid"

cat >> "$pgdata/postgresql.auto.conf" <<EOF
restore_command = 'cp $archive_dir/%f %p'
recovery_target_timeline = 'latest'
EOF
if [[ -n "$target_name" ]]; then
  cat >> "$pgdata/postgresql.auto.conf" <<EOF
recovery_target_name = '$target_name'
recovery_target_action = 'promote'
EOF
fi

touch "$pgdata/recovery.signal"
chown -R postgres:postgres "$pgdata"
chmod 0700 "$pgdata"

echo "[recovery] isolated restore initialized${target_name:+ to restore point $target_name}"
exec /usr/local/bin/docker-entrypoint.sh "$@"

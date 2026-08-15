#!/usr/bin/env bash
set -Eeuo pipefail

archive_dir="${LUMI_WAL_ARCHIVE_DIR:-/var/lib/postgresql/wal-archive}"
mkdir -p "$archive_dir"
chown postgres:postgres "$archive_dir"
chmod 0700 "$archive_dir"

exec /usr/local/bin/docker-entrypoint.sh "$@"

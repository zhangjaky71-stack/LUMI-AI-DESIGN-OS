#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <source-bucket> <destination-bucket> <destination-region> <key> <version-id> [version-id ...]" >&2
  exit 64
}

[[ $# -ge 5 ]] || usage
SOURCE_BUCKET="$1"
DESTINATION_BUCKET="$2"
DESTINATION_REGION="$3"
KEY="$4"
shift 4
VERSION_IDS=("$@")

[[ -n "${AWS_REGION:-}" ]] || { echo "AWS_REGION is required" >&2; exit 64; }
[[ -n "$DESTINATION_REGION" && "$DESTINATION_REGION" != "$AWS_REGION" ]] || {
  echo "destination region must differ from AWS_REGION" >&2
  exit 64
}
[[ "$KEY" == _node73-drill/* ]] || { echo "refusing to clean non-drill key" >&2; exit 64; }
[[ ${#VERSION_IDS[@]} -ge 1 ]] || { echo "at least one source VersionId required" >&2; exit 64; }

for version_id in "${VERSION_IDS[@]}"; do
  [[ -n "$version_id" && "$version_id" != "null" ]] || { echo "invalid source VersionId" >&2; exit 64; }
  status=""
  for _ in $(seq 1 60); do
    status="$(aws s3api head-object \
      --region "$AWS_REGION" \
      --bucket "$SOURCE_BUCKET" \
      --key "$KEY" \
      --version-id "$version_id" \
      --query ReplicationStatus \
      --output text 2>/dev/null || true)"
    [[ "$status" == "COMPLETED" ]] && break
    [[ "$status" == "FAILED" ]] && { echo "source version replication failed: $version_id" >&2; exit 65; }
    sleep 15
  done
  [[ "$status" == "COMPLETED" ]] || {
    echo "source version did not reach replication COMPLETED within RTC window: $version_id ($status)" >&2
    exit 65
  }
done

# COMPLETED on every source version means the destination replicas exist. Purge
# only this deterministic NODE-73 drill key; never accept a broad prefix here.
listing="$(aws s3api list-object-versions \
  --region "$DESTINATION_REGION" \
  --bucket "$DESTINATION_BUCKET" \
  --prefix "$KEY")"
replica_count="$(jq --arg key "$KEY" '[.Versions[]? | select(.Key == $key)] | length' <<<"$listing")"
[[ "$replica_count" -ge ${#VERSION_IDS[@]} ]] || {
  echo "destination does not contain all completed drill replicas" >&2
  exit 66
}

deletes="$(jq -c --arg key "$KEY" '[
  (.Versions // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId},
  (.DeleteMarkers // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId}
]' <<<"$listing")"
[[ "$deletes" != "[]" ]] || { echo "destination drill replicas unexpectedly empty" >&2; exit 66; }

aws s3api delete-objects \
  --region "$DESTINATION_REGION" \
  --bucket "$DESTINATION_BUCKET" \
  --delete "$(jq -n --argjson objects "$deletes" '{Objects:$objects,Quiet:true}')" \
  >/dev/null

after="$(aws s3api list-object-versions \
  --region "$DESTINATION_REGION" \
  --bucket "$DESTINATION_BUCKET" \
  --prefix "$KEY")"
remaining="$(jq --arg key "$KEY" '[
  (.Versions // [])[] | select(.Key == $key),
  (.DeleteMarkers // [])[] | select(.Key == $key)
] | length' <<<"$after")"
[[ "$remaining" -eq 0 ]] || { echo "destination drill cleanup incomplete" >&2; exit 67; }

echo "replicated object recovery drill cleanup: PASS"

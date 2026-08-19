#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <versioned-bucket> <deployment-id> <run-id> <output-json>" >&2
  exit 64
}

[[ $# -eq 4 ]] || usage
BUCKET="$1"
DEPLOYMENT_ID="$2"
RUN_ID="$3"
OUTPUT_JSON="$4"
[[ "$DEPLOYMENT_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid deployment id" >&2; exit 64; }
[[ "$RUN_ID" =~ ^[0-9]+$ ]] || { echo "invalid run id" >&2; exit 64; }
mkdir -p "$(dirname "$OUTPUT_JSON")"

VERSIONING="$(aws s3api get-bucket-versioning --bucket "$BUCKET" --query Status --output text)"
[[ "$VERSIONING" == "Enabled" ]] || { echo "object recovery drill requires bucket versioning=Enabled" >&2; exit 65; }

# Production DR owns one canonical critical-bucket topology. Resolve it before
# writing drill data so the EXIT trap can also remove any replicas after an
# intermediate failure.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$REPO_ROOT/infra/iac/environments/production/core"
SOURCE_BUCKETS="$(terraform -chdir="$CORE_DIR" output -json bucket_names)"
DR_BUCKETS="$(terraform -chdir="$CORE_DIR" output -json object_dr_bucket_names)"
DR_REGION="$(terraform -chdir="$CORE_DIR" output -raw object_dr_region)"
CANONICAL_EXPORTS="$(jq -r '.exports' <<<"$SOURCE_BUCKETS")"
DR_EXPORTS="$(jq -r '.exports' <<<"$DR_BUCKETS")"
[[ "$BUCKET" == "$CANONICAL_EXPORTS" ]] || {
  echo "production object version drill must target the canonical exports bucket" >&2
  exit 65
}
[[ -n "${AWS_REGION:-}" && -n "$DR_REGION" && "$AWS_REGION" != "$DR_REGION" ]] || {
  echo "cross-region object recovery outputs are missing or not cross-region" >&2
  exit 65
}

KEY="_node73-drill/${DEPLOYMENT_ID}/${RUN_ID}/object-recovery.txt"
TMP_DIR="$(mktemp -d)"
V1_FILE="$TMP_DIR/v1"
V2_FILE="$TMP_DIR/v2"
RECOVERED_FILE="$TMP_DIR/recovered"
CURRENT_FILE="$TMP_DIR/current"
CROSS_REGION_FILE="$TMP_DIR/cross-region.json"
CLEANED=false

purge_exact_key() {
  local bucket="$1" region="$2" key="$3"
  local listing deletes
  listing="$(aws s3api list-object-versions --region "$region" --bucket "$bucket" --prefix "$key" 2>/dev/null || true)"
  deletes="$(jq -c --arg key "$key" '[
    (.Versions // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId},
    (.DeleteMarkers // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId}
  ]' <<<"${listing:-{}}" 2>/dev/null || true)"
  if [[ -n "$deletes" && "$deletes" != "[]" ]]; then
    aws s3api delete-objects \
      --region "$region" \
      --bucket "$bucket" \
      --delete "$(jq -n --argjson objects "$deletes" '{Objects:$objects,Quiet:true}')" \
      >/dev/null 2>&1 || true
  fi
}

cleanup() {
  local exit_code=$?
  if [[ "$CLEANED" != true ]]; then
    set +e
    purge_exact_key "$BUCKET" "$AWS_REGION" "$KEY"
    purge_exact_key "$DR_EXPORTS" "$DR_REGION" "$KEY"
    rm -rf "$TMP_DIR"
    set -e
  fi
  return "$exit_code"
}
trap cleanup EXIT

printf 'lumi-node73-object-recovery-v1:%s:%s\n' "$DEPLOYMENT_ID" "$RUN_ID" > "$V1_FILE"
printf 'lumi-node73-object-recovery-corrupt-v2:%s:%s\n' "$DEPLOYMENT_ID" "$RUN_ID" > "$V2_FILE"
V1_SHA="$(sha256sum "$V1_FILE" | awk '{print $1}')"
V2_SHA="$(sha256sum "$V2_FILE" | awk '{print $1}')"
[[ "$V1_SHA" != "$V2_SHA" ]] || { echo "fixture checksums unexpectedly equal" >&2; exit 66; }

V1_RESPONSE="$(aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$V1_FILE" --content-type text/plain)"
V1_VERSION="$(jq -r '.VersionId // empty' <<<"$V1_RESPONSE")"
[[ -n "$V1_VERSION" && "$V1_VERSION" != "null" ]] || { echo "v1 VersionId missing" >&2; exit 66; }

V2_RESPONSE="$(aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$V2_FILE" --content-type text/plain)"
V2_VERSION="$(jq -r '.VersionId // empty' <<<"$V2_RESPONSE")"
[[ -n "$V2_VERSION" && "$V2_VERSION" != "$V1_VERSION" ]] || { echo "v2 VersionId invalid" >&2; exit 66; }

DELETE_RESPONSE="$(aws s3api delete-object --bucket "$BUCKET" --key "$KEY")"
DELETE_MARKER="$(jq -r '.DeleteMarker // false' <<<"$DELETE_RESPONSE")"
DELETE_VERSION="$(jq -r '.VersionId // empty' <<<"$DELETE_RESPONSE")"
[[ "$DELETE_MARKER" == true && -n "$DELETE_VERSION" ]] || { echo "expected versioned delete marker" >&2; exit 67; }

if aws s3api head-object --bucket "$BUCKET" --key "$KEY" >/dev/null 2>&1; then
  echo "delete marker did not hide current object" >&2
  exit 67
fi

aws s3api get-object --bucket "$BUCKET" --key "$KEY" --version-id "$V1_VERSION" "$RECOVERED_FILE" >/dev/null
RECOVERED_SHA="$(sha256sum "$RECOVERED_FILE" | awk '{print $1}')"
[[ "$RECOVERED_SHA" == "$V1_SHA" ]] || { echo "historical v1 checksum mismatch" >&2; exit 68; }

RESTORE_RESPONSE="$(aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$RECOVERED_FILE" --content-type text/plain)"
RESTORED_VERSION="$(jq -r '.VersionId // empty' <<<"$RESTORE_RESPONSE")"
[[ -n "$RESTORED_VERSION" && "$RESTORED_VERSION" != "$V1_VERSION" && "$RESTORED_VERSION" != "$V2_VERSION" ]] || {
  echo "restored current VersionId invalid" >&2
  exit 68
}

aws s3api get-object --bucket "$BUCKET" --key "$KEY" "$CURRENT_FILE" >/dev/null
CURRENT_SHA="$(sha256sum "$CURRENT_FILE" | awk '{print $1}')"
[[ "$CURRENT_SHA" == "$V1_SHA" ]] || { echo "restored current checksum mismatch" >&2; exit 68; }

VERSIONS_BEFORE_CLEANUP="$(aws s3api list-object-versions --bucket "$BUCKET" --prefix "$KEY")"
VERSION_COUNT="$(jq --arg key "$KEY" '[.Versions[]? | select(.Key == $key)] | length' <<<"$VERSIONS_BEFORE_CLEANUP")"
MARKER_COUNT="$(jq --arg key "$KEY" '[.DeleteMarkers[]? | select(.Key == $key)] | length' <<<"$VERSIONS_BEFORE_CLEANUP")"
[[ "$VERSION_COUNT" -ge 3 && "$MARKER_COUNT" -ge 1 ]] || { echo "version history incomplete before cleanup" >&2; exit 69; }

# Delete-marker replication is disabled by design, but the three data versions
# are critical-bucket writes and therefore replicate. Require all three source
# versions to finish CRR and then purge their exact destination key before the
# source versions are permanently removed.
bash "$REPO_ROOT/scripts/cleanup-production-object-dr-replicas.sh" \
  "$BUCKET" \
  "$DR_EXPORTS" \
  "$DR_REGION" \
  "$KEY" \
  "$V1_VERSION" "$V2_VERSION" "$RESTORED_VERSION"

DELETES="$(jq -c --arg key "$KEY" '[
  (.Versions // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId},
  (.DeleteMarkers // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId}
]' <<<"$VERSIONS_BEFORE_CLEANUP")"
aws s3api delete-objects --bucket "$BUCKET" --delete "$(jq -n --argjson objects "$DELETES" '{Objects:$objects,Quiet:true}')" >/dev/null

AFTER="$(aws s3api list-object-versions --bucket "$BUCKET" --prefix "$KEY")"
REMAINING="$(jq --arg key "$KEY" '[
  (.Versions // [])[] | select(.Key == $key),
  (.DeleteMarkers // [])[] | select(.Key == $key)
] | length' <<<"$AFTER")"
[[ "$REMAINING" -eq 0 ]] || { echo "drill cleanup left source object versions behind" >&2; exit 70; }
DR_AFTER="$(aws s3api list-object-versions --region "$DR_REGION" --bucket "$DR_EXPORTS" --prefix "$KEY")"
DR_REMAINING="$(jq --arg key "$KEY" '[
  (.Versions // [])[] | select(.Key == $key),
  (.DeleteMarkers // [])[] | select(.Key == $key)
] | length' <<<"$DR_AFTER")"
[[ "$DR_REMAINING" -eq 0 ]] || { echo "drill cleanup left destination replicas behind" >&2; exit 70; }
CLEANED=true

bash "$REPO_ROOT/scripts/production-object-cross-region-drill.sh" \
  "$(jq -r '.assets' <<<"$SOURCE_BUCKETS")" \
  "$(jq -r '.assets' <<<"$DR_BUCKETS")" \
  "$(jq -r '.exports' <<<"$SOURCE_BUCKETS")" \
  "$DR_EXPORTS" \
  "$DR_REGION" \
  "$DEPLOYMENT_ID" \
  "$RUN_ID" \
  "$CROSS_REGION_FILE"

test "$(jq -r '.passed' "$CROSS_REGION_FILE")" = true

jq -n \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg bucket "$BUCKET" \
  --arg key "$KEY" \
  --arg v1_version_id "$V1_VERSION" \
  --arg corrupt_version_id "$V2_VERSION" \
  --arg delete_marker_version_id "$DELETE_VERSION" \
  --arg restored_version_id "$RESTORED_VERSION" \
  --arg expected_sha256 "$V1_SHA" \
  --arg corrupt_sha256 "$V2_SHA" \
  --arg restored_sha256 "$CURRENT_SHA" \
  --argjson version_count_before_cleanup "$VERSION_COUNT" \
  --argjson delete_marker_count_before_cleanup "$MARKER_COUNT" \
  --slurpfile cross_region "$CROSS_REGION_FILE" \
  '{schema_version:1,deployment_id:$deployment_id,bucket:$bucket,key:$key,versioning:"Enabled",expected_sha256:$expected_sha256,corrupt_sha256:$corrupt_sha256,restored_sha256:$restored_sha256,v1_version_id:$v1_version_id,corrupt_version_id:$corrupt_version_id,delete_marker_version_id:$delete_marker_version_id,restored_version_id:$restored_version_id,version_count_before_cleanup:$version_count_before_cleanup,delete_marker_count_before_cleanup:$delete_marker_count_before_cleanup,cleanup_complete:true,replica_cleanup_complete:true,cross_region:$cross_region[0],passed:($expected_sha256 == $restored_sha256 and $cross_region[0].passed == true)}' \
  > "$OUTPUT_JSON"

test "$(jq -r '.passed' "$OUTPUT_JSON")" = true
rm -rf "$TMP_DIR"
trap - EXIT

echo "production object recovery drill: PASS"

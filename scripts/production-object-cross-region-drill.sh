#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <source-assets> <dr-assets> <source-exports> <dr-exports> <dr-region> <deployment-id> <run-id> <output-json>" >&2
  exit 64
}

[[ $# -eq 8 ]] || usage
SOURCE_ASSETS="$1"
DR_ASSETS="$2"
SOURCE_EXPORTS="$3"
DR_EXPORTS="$4"
DR_REGION="$5"
DEPLOYMENT_ID="$6"
RUN_ID="$7"
OUTPUT_JSON="$8"

[[ "$DEPLOYMENT_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid deployment id" >&2; exit 64; }
[[ "$RUN_ID" =~ ^[0-9]+$ ]] || { echo "invalid run id" >&2; exit 64; }
[[ -n "${AWS_REGION:-}" && -n "$DR_REGION" && "$DR_REGION" != "$AWS_REGION" ]] || {
  echo "cross-region drill requires distinct AWS_REGION and DR region" >&2
  exit 64
}
mkdir -p "$(dirname "$OUTPUT_JSON")"

TMP_DIR="$(mktemp -d)"
RESULTS="$TMP_DIR/results.ndjson"
CLEANUP_COMPLETE=false

cleanup_key() {
  local bucket="$1" region="$2" key="$3"
  local listing deletes remaining
  listing="$(aws s3api list-object-versions --region "$region" --bucket "$bucket" --prefix "$key")"
  deletes="$(jq -c --arg key "$key" '[
    (.Versions // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId},
    (.DeleteMarkers // [])[] | select(.Key == $key) | {Key:.Key,VersionId:.VersionId}
  ]' <<<"$listing")"
  if [[ "$deletes" != "[]" ]]; then
    aws s3api delete-objects \
      --region "$region" \
      --bucket "$bucket" \
      --delete "$(jq -n --argjson objects "$deletes" '{Objects:$objects,Quiet:true}')" \
      >/dev/null
  fi
  listing="$(aws s3api list-object-versions --region "$region" --bucket "$bucket" --prefix "$key")"
  remaining="$(jq --arg key "$key" '[
    (.Versions // [])[] | select(.Key == $key),
    (.DeleteMarkers // [])[] | select(.Key == $key)
  ] | length' <<<"$listing")"
  [[ "$remaining" -eq 0 ]]
}

best_effort_cleanup() {
  local exit_code=$?
  if [[ "$CLEANUP_COMPLETE" != true ]]; then
    set +e
    for purpose in assets exports; do
      if [[ "$purpose" == assets ]]; then
        source="$SOURCE_ASSETS"; destination="$DR_ASSETS"
      else
        source="$SOURCE_EXPORTS"; destination="$DR_EXPORTS"
      fi
      key="_node73-drill/${DEPLOYMENT_ID}/${RUN_ID}/cross-region/${purpose}.txt"
      cleanup_key "$source" "$AWS_REGION" "$key" >/dev/null 2>&1
      cleanup_key "$destination" "$DR_REGION" "$key" >/dev/null 2>&1
    done
    rm -rf "$TMP_DIR"
    set -e
  fi
  return "$exit_code"
}
trap best_effort_cleanup EXIT

verify_bucket_contract() {
  local purpose="$1" source="$2" destination="$3"
  local source_versioning destination_versioning replication rule_id destination_arn

  source_versioning="$(aws s3api get-bucket-versioning --region "$AWS_REGION" --bucket "$source" --query Status --output text)"
  destination_versioning="$(aws s3api get-bucket-versioning --region "$DR_REGION" --bucket "$destination" --query Status --output text)"
  [[ "$source_versioning" == "Enabled" && "$destination_versioning" == "Enabled" ]] || {
    echo "$purpose source/destination versioning must be Enabled" >&2
    return 1
  }

  replication="$(aws s3api get-bucket-replication --region "$AWS_REGION" --bucket "$source")"
  rule_id="lumi-${purpose}-cross-region-dr"
  destination_arn="arn:aws:s3:::${destination}"
  jq -e \
    --arg id "$rule_id" \
    --arg destination "$destination_arn" \
    '.ReplicationConfiguration.Rules
      | any(
          .ID == $id
          and .Status == "Enabled"
          and .Destination.Bucket == $destination
          and .DeleteMarkerReplication.Status == "Disabled"
          and .SourceSelectionCriteria.SseKmsEncryptedObjects.Status == "Enabled"
          and .Destination.ReplicationTime.Status == "Enabled"
          and .Destination.ReplicationTime.Time.Minutes == 15
          and .Destination.Metrics.Status == "Enabled"
          and .Destination.Metrics.EventThreshold.Minutes == 15
        )' <<<"$replication" >/dev/null || {
          echo "$purpose replication configuration does not match CRR+RTC contract" >&2
          return 1
        }
}

exercise_pair() {
  local purpose="$1" source="$2" destination="$3"
  local key source_file destination_file expected_sha put version_id started now elapsed
  local source_status destination_status destination_sha

  verify_bucket_contract "$purpose" "$source" "$destination"

  key="_node73-drill/${DEPLOYMENT_ID}/${RUN_ID}/cross-region/${purpose}.txt"
  source_file="$TMP_DIR/${purpose}-source"
  destination_file="$TMP_DIR/${purpose}-destination"
  printf 'lumi-node73-cross-region:%s:%s:%s\n' "$DEPLOYMENT_ID" "$RUN_ID" "$purpose" > "$source_file"
  expected_sha="$(sha256sum "$source_file" | awk '{print $1}')"
  started="$(date +%s)"

  put="$(aws s3api put-object \
    --region "$AWS_REGION" \
    --bucket "$source" \
    --key "$key" \
    --body "$source_file" \
    --content-type text/plain)"
  version_id="$(jq -r '.VersionId // empty' <<<"$put")"
  [[ -n "$version_id" && "$version_id" != "null" ]] || { echo "$purpose source VersionId missing" >&2; return 1; }

  destination_status=""
  source_status=""
  elapsed=0
  for _ in $(seq 1 60); do
    now="$(date +%s)"
    elapsed=$((now - started))
    source_status="$(aws s3api head-object \
      --region "$AWS_REGION" --bucket "$source" --key "$key" --version-id "$version_id" \
      --query ReplicationStatus --output text 2>/dev/null || true)"
    destination_status="$(aws s3api head-object \
      --region "$DR_REGION" --bucket "$destination" --key "$key" \
      --query ReplicationStatus --output text 2>/dev/null || true)"
    if [[ "$source_status" == "COMPLETED" && "$destination_status" == "REPLICA" ]]; then
      break
    fi
    sleep 15
  done

  [[ "$source_status" == "COMPLETED" ]] || { echo "$purpose source replication status is $source_status" >&2; return 1; }
  [[ "$destination_status" == "REPLICA" ]] || { echo "$purpose destination replication status is $destination_status" >&2; return 1; }
  [[ "$elapsed" -le 900 ]] || { echo "$purpose replication exceeded 15-minute RTC threshold: ${elapsed}s" >&2; return 1; }

  aws s3api get-object --region "$DR_REGION" --bucket "$destination" --key "$key" "$destination_file" >/dev/null
  destination_sha="$(sha256sum "$destination_file" | awk '{print $1}')"
  [[ "$destination_sha" == "$expected_sha" ]] || { echo "$purpose replica checksum mismatch" >&2; return 1; }

  jq -n \
    --arg purpose "$purpose" \
    --arg source_bucket "$source" \
    --arg destination_bucket "$destination" \
    --arg source_region "$AWS_REGION" \
    --arg destination_region "$DR_REGION" \
    --arg key "$key" \
    --arg source_version_id "$version_id" \
    --arg source_replication_status "$source_status" \
    --arg destination_replication_status "$destination_status" \
    --arg expected_sha256 "$expected_sha" \
    --arg destination_sha256 "$destination_sha" \
    --argjson replication_lag_seconds "$elapsed" \
    '{purpose:$purpose,source_bucket:$source_bucket,destination_bucket:$destination_bucket,source_region:$source_region,destination_region:$destination_region,key:$key,source_version_id:$source_version_id,source_replication_status:$source_replication_status,destination_replication_status:$destination_replication_status,expected_sha256:$expected_sha256,destination_sha256:$destination_sha256,replication_lag_seconds:$replication_lag_seconds,rtc_minutes:15,passed:($expected_sha256 == $destination_sha256 and $replication_lag_seconds <= 900)}' \
    >> "$RESULTS"
}

exercise_pair assets "$SOURCE_ASSETS" "$DR_ASSETS"
exercise_pair exports "$SOURCE_EXPORTS" "$DR_EXPORTS"

for purpose in assets exports; do
  if [[ "$purpose" == assets ]]; then
    source="$SOURCE_ASSETS"; destination="$DR_ASSETS"
  else
    source="$SOURCE_EXPORTS"; destination="$DR_EXPORTS"
  fi
  key="_node73-drill/${DEPLOYMENT_ID}/${RUN_ID}/cross-region/${purpose}.txt"
  cleanup_key "$source" "$AWS_REGION" "$key"
  cleanup_key "$destination" "$DR_REGION" "$key"
done
CLEANUP_COMPLETE=true

jq -s \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg source_region "$AWS_REGION" \
  --arg destination_region "$DR_REGION" \
  '{schema_version:1,deployment_id:$deployment_id,source_region:$source_region,destination_region:$destination_region,rtc_minutes:15,pairs:.,max_replication_lag_seconds:(map(.replication_lag_seconds)|max),cleanup_complete:true,passed:(length == 2 and all(.[]; .passed == true) and $source_region != $destination_region)}' \
  "$RESULTS" > "$OUTPUT_JSON"

test "$(jq -r '.passed' "$OUTPUT_JSON")" = true
rm -rf "$TMP_DIR"
trap - EXIT

echo "production cross-region object recovery drill: PASS"

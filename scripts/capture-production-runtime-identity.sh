#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-app-dir> <deployment-manifest-json> <output-json> [capacity-contract-deployment-id]" >&2
  exit 64
}

[[ $# -ge 3 && $# -le 4 ]] || usage
APP_DIR="$1"
MANIFEST="$2"
OUTPUT_JSON="$3"
CAPACITY_CONTRACT_DEPLOYMENT_ID="${4:-}"
mkdir -p "$(dirname "$OUTPUT_JSON")"

[[ -f "$MANIFEST" ]] || { echo "deployment manifest missing" >&2; exit 64; }
DEPLOYMENT_ID="$(jq -r '.deployment_id // empty' "$MANIFEST")"
RC_SHA="$(jq -r '.release_candidate.git_sha // empty' "$MANIFEST")"
RC_VERSION="$(jq -r '.release_candidate.version // empty' "$MANIFEST")"
MIGRATION_HEAD="$(jq -r '.release_candidate.migration_head // empty' "$MANIFEST")"
EXPECTED_IMAGES="$(jq -c '.images // {}' "$MANIFEST")"

[[ -n "$DEPLOYMENT_ID" && -n "$RC_SHA" && -n "$RC_VERSION" && -n "$MIGRATION_HEAD" ]] || {
  echo "deployment manifest identity incomplete" >&2
  exit 65
}
if [[ -z "$CAPACITY_CONTRACT_DEPLOYMENT_ID" ]]; then
  CAPACITY_CONTRACT_DEPLOYMENT_ID="$DEPLOYMENT_ID"
fi
[[ -n "$CAPACITY_CONTRACT_DEPLOYMENT_ID" ]] || {
  echo "capacity contract deployment identity missing" >&2
  exit 65
}

EXPECTED_IMAGE_KEYS='["agent-runtime","api","model-gateway","sandbox-runtime","tool-gateway","worker-media"]'
EXPECTED_SERVICES='["agent-runtime","api","model-gateway","outbox-dispatcher","sandbox-runtime","tool-gateway","worker-media"]'
if [[ "$(jq -c 'keys | sort' <<<"$EXPECTED_IMAGES")" != "$EXPECTED_IMAGE_KEYS" ]]; then
  echo "deployment manifest must contain exactly six runtime images" >&2
  exit 65
fi

CLUSTER_ARN="$(terraform -chdir="$APP_DIR" output -raw cluster_arn)"
SERVICES_JSON="$(terraform -chdir="$APP_DIR" output -json service_names)"
EXPECTED_CAPACITY_JSON="$(terraform -chdir="$APP_DIR" output -json service_desired_counts)"
EXPECTED_CAPACITY_CANONICAL="$(jq -c 'to_entries | sort_by(.key) | from_entries' <<<"$EXPECTED_CAPACITY_JSON")"
mapfile -t SERVICES < <(jq -r '.[]' <<<"$SERVICES_JSON")

[[ -n "$CLUSTER_ARN" && "$CLUSTER_ARN" != "null" ]] || { echo "cluster_arn missing" >&2; exit 65; }
[[ ${#SERVICES[@]} -eq 7 ]] || { echo "expected exactly seven ECS services" >&2; exit 65; }

ACTUAL_SERVICES="$(printf '%s\n' "${SERVICES[@]}" | jq -R . | jq -sc 'sort')"
[[ "$ACTUAL_SERVICES" == "$EXPECTED_SERVICES" ]] || {
  echo "ECS service set does not match canonical six-image/seven-service contract" >&2
  exit 66
}
[[ "$(jq -c 'keys | sort' <<<"$EXPECTED_CAPACITY_CANONICAL")" == "$EXPECTED_SERVICES" ]] || {
  echo "Terraform expected capacity set does not match canonical seven-service contract" >&2
  exit 66
}
if ! jq -e 'all(.[]; (type == "number") and (floor == .) and (. > 0))' <<<"$EXPECTED_CAPACITY_CANONICAL" >/dev/null; then
  echo "Terraform expected capacity values must be positive integers" >&2
  exit 66
fi

DESCRIPTION="$(aws ecs describe-services --cluster "$CLUSTER_ARN" --services "${SERVICES[@]}")"
[[ "$(jq '.failures | length' <<<"$DESCRIPTION")" -eq 0 ]] || {
  echo "ECS describe-services returned failures" >&2
  exit 66
}

ROWS='[]'
PASSED=true
for service in "${SERVICES[@]}"; do
  SERVICE_JSON="$(jq -c --arg name "$service" '.services[] | select(.serviceName == $name)' <<<"$DESCRIPTION")"
  [[ -n "$SERVICE_JSON" ]] || { echo "missing ECS service $service" >&2; exit 66; }

  IMAGE_KEY="$service"
  if [[ "$service" == "outbox-dispatcher" ]]; then
    IMAGE_KEY="worker-media"
  fi

  TASK_DEFINITION="$(jq -r '.taskDefinition' <<<"$SERVICE_JSON")"
  TASK_JSON="$(aws ecs describe-task-definition --task-definition "$TASK_DEFINITION")"
  IMAGE="$(jq -r --arg name "$service" '.taskDefinition.containerDefinitions[] | select(.name == $name) | .image // empty' <<<"$TASK_JSON")"
  EXPECTED_IMAGE="$(jq -r --arg name "$IMAGE_KEY" '.[$name] // empty' <<<"$EXPECTED_IMAGES")"
  EXPECTED_DESIRED="$(jq -r --arg name "$service" '.[$name] // empty' <<<"$EXPECTED_CAPACITY_CANONICAL")"
  PRIMARY="$(jq -c '[.deployments[] | select(.status == "PRIMARY")][0] // null' <<<"$SERVICE_JSON")"
  STATUS="$(jq -r '.status' <<<"$SERVICE_JSON")"
  DESIRED="$(jq -r '.desiredCount' <<<"$SERVICE_JSON")"
  RUNNING="$(jq -r '.runningCount' <<<"$SERVICE_JSON")"
  PENDING="$(jq -r '.pendingCount' <<<"$SERVICE_JSON")"
  ROLLOUT="$(jq -r '(.rolloutState // "COMPLETED")' <<<"$PRIMARY")"

  [[ "$EXPECTED_DESIRED" =~ ^[1-9][0-9]*$ ]] || {
    echo "invalid Terraform expected desired count for $service" >&2
    exit 66
  }

  MATCHED=false
  if [[ -n "$IMAGE" && "$IMAGE" == "$EXPECTED_IMAGE" ]]; then
    MATCHED=true
  fi
  CAPACITY_MATCHED=false
  if [[ "$DESIRED" -eq "$EXPECTED_DESIRED" ]]; then
    CAPACITY_MATCHED=true
  fi
  STEADY=false
  if [[ "$STATUS" == "ACTIVE" && "$CAPACITY_MATCHED" == true && "$RUNNING" -eq "$DESIRED" && "$PENDING" -eq 0 && "$ROLLOUT" == "COMPLETED" ]]; then
    STEADY=true
  fi
  if [[ "$MATCHED" != true || "$CAPACITY_MATCHED" != true || "$STEADY" != true ]]; then
    PASSED=false
  fi

  ROW="$(jq -n \
    --arg service_name "$service" \
    --arg image_key "$IMAGE_KEY" \
    --arg task_definition "$TASK_DEFINITION" \
    --arg image "$IMAGE" \
    --arg expected_image "$EXPECTED_IMAGE" \
    --arg status "$STATUS" \
    --arg rollout_state "$ROLLOUT" \
    --argjson expected_desired_count "$EXPECTED_DESIRED" \
    --argjson desired_count "$DESIRED" \
    --argjson running_count "$RUNNING" \
    --argjson pending_count "$PENDING" \
    --argjson image_matches "$MATCHED" \
    --argjson capacity_matches "$CAPACITY_MATCHED" \
    --argjson steady "$STEADY" \
    '{service_name:$service_name,image_key:$image_key,task_definition:$task_definition,image:$image,expected_image:$expected_image,image_matches:$image_matches,expected_desired_count:$expected_desired_count,capacity_matches:$capacity_matches,status:$status,rollout_state:$rollout_state,desired_count:$desired_count,running_count:$running_count,pending_count:$pending_count,steady:$steady}')"
  ROWS="$(jq -c --argjson row "$ROW" '. + [$row]' <<<"$ROWS")"
done

jq -n \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg git_sha "$RC_SHA" \
  --arg version "$RC_VERSION" \
  --arg migration_head "$MIGRATION_HEAD" \
  --arg cluster_arn "$CLUSTER_ARN" \
  --arg capacity_contract_deployment_id "$CAPACITY_CONTRACT_DEPLOYMENT_ID" \
  --arg capacity_contract_source "terraform-live-state" \
  --arg capacity_contract_scope "production-app-service-desired-counts" \
  --argjson capacity_contract_service_desired_counts "$EXPECTED_CAPACITY_CANONICAL" \
  --argjson services "$(jq -c 'sort_by(.service_name)' <<<"$ROWS")" \
  --argjson passed "$PASSED" \
  '{schema_version:1,deployment_id:$deployment_id,release_candidate:{git_sha:$git_sha,version:$version,migration_head:$migration_head},cluster_arn:$cluster_arn,capacity_contract:{schema_version:1,source:$capacity_contract_source,scope:$capacity_contract_scope,deployment_id:$capacity_contract_deployment_id,service_desired_counts:$capacity_contract_service_desired_counts},passed:$passed,services:$services}' \
  > "$OUTPUT_JSON"

if [[ "$PASSED" != true ]]; then
  echo "production runtime identity/steady-state verification failed" >&2
  exit 67
fi

echo "production runtime identity: PASS"

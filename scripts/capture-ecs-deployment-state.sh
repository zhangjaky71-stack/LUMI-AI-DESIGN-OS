#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-app-dir> <output-json>" >&2
  exit 64
}

[[ $# -eq 2 ]] || usage
APP_DIR="$1"
OUTPUT_JSON="$2"
mkdir -p "$(dirname "$OUTPUT_JSON")"

CLUSTER_ARN="$(terraform -chdir="$APP_DIR" output -raw cluster_arn)"
SERVICES_JSON="$(terraform -chdir="$APP_DIR" output -json service_names)"
mapfile -t SERVICES < <(jq -r '.[]' <<<"$SERVICES_JSON")

[[ -n "$CLUSTER_ARN" && "$CLUSTER_ARN" != "null" ]] || { echo "cluster_arn missing" >&2; exit 65; }
[[ ${#SERVICES[@]} -gt 0 ]] || { echo "service_names empty" >&2; exit 65; }

DESCRIPTION="$(aws ecs describe-services --cluster "$CLUSTER_ARN" --services "${SERVICES[@]}")"
FAILURES="$(jq '.failures | length' <<<"$DESCRIPTION")"
[[ "$FAILURES" -eq 0 ]] || { echo "ECS describe-services returned failures" >&2; exit 66; }

NORMALIZED="$(jq '[.services[] | {
  service_name: .serviceName,
  status: .status,
  desired_count: .desiredCount,
  running_count: .runningCount,
  pending_count: .pendingCount,
  task_definition: .taskDefinition,
  primary_deployment: ([.deployments[] | select(.status == "PRIMARY")][0] // null),
  deployments: [.deployments[] | {
    id: .id,
    status: .status,
    rollout_state: (.rolloutState // null),
    rollout_state_reason: (.rolloutStateReason // null),
    desired_count: .desiredCount,
    running_count: .runningCount,
    pending_count: .pendingCount,
    task_definition: .taskDefinition
  }]
}]' <<<"$DESCRIPTION")"

PASSED="$(jq 'all(.[];
  .status == "ACTIVE" and
  .desired_count > 0 and
  .running_count == .desired_count and
  .pending_count == 0 and
  (.primary_deployment != null) and
  ((.primary_deployment.rolloutState // "COMPLETED") == "COMPLETED")
)' <<<"$NORMALIZED")"

jq -n \
  --arg cluster_arn "$CLUSTER_ARN" \
  --argjson services "$NORMALIZED" \
  --argjson passed "$PASSED" \
  '{schema_version:1,cluster_arn:$cluster_arn,passed:$passed,services:$services}' > "$OUTPUT_JSON"

if [[ "$PASSED" != "true" ]]; then
  echo "one or more ECS services are not at verified steady state" >&2
  exit 67
fi

echo "ECS deployment state: PASS"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-app-dir> <deployment-id> <output-json>" >&2
  exit 64
}

[[ $# -eq 3 ]] || usage
APP_DIR="$1"
DEPLOYMENT_ID="$2"
OUTPUT_JSON="$3"

[[ "$DEPLOYMENT_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid deployment id" >&2; exit 64; }
mkdir -p "$(dirname "$OUTPUT_JSON")"

TASK_DEFINITION="$(terraform -chdir="$APP_DIR" output -raw migration_task_definition_arn)"
NETWORK_JSON="$(terraform -chdir="$APP_DIR" output -json migration_network)"
CLUSTER_ARN="$(jq -r '.cluster_arn' <<<"$NETWORK_JSON")"
SECURITY_GROUP="$(jq -r '.security_group_id' <<<"$NETWORK_JSON")"
SUBNETS_CSV="$(jq -r '.private_subnet_ids | join(",")' <<<"$NETWORK_JSON")"

for value in "$TASK_DEFINITION" "$CLUSTER_ARN" "$SECURITY_GROUP" "$SUBNETS_CSV"; do
  [[ -n "$value" && "$value" != "null" ]] || { echo "migration execution metadata missing" >&2; exit 65; }
done

TASK_ARN="$(aws ecs run-task \
  --cluster "$CLUSTER_ARN" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEFINITION" \
  --started-by "lumi-$DEPLOYMENT_ID" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_CSV],securityGroups=[$SECURITY_GROUP],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' \
  --output text)"

[[ -n "$TASK_ARN" && "$TASK_ARN" != "None" ]] || { echo "ECS did not return a migration task ARN" >&2; exit 66; }
aws ecs wait tasks-stopped --cluster "$CLUSTER_ARN" --tasks "$TASK_ARN"

DESCRIPTION="$(aws ecs describe-tasks --cluster "$CLUSTER_ARN" --tasks "$TASK_ARN")"
EXIT_CODE="$(jq -r '.tasks[0].containers[] | select(.name == "migration") | .exitCode // -1' <<<"$DESCRIPTION")"
STOP_REASON="$(jq -r '.tasks[0].stoppedReason // "unknown"' <<<"$DESCRIPTION")"
CONTAINER_REASON="$(jq -r '.tasks[0].containers[] | select(.name == "migration") | .reason // ""' <<<"$DESCRIPTION")"

jq -n \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg task_arn "$TASK_ARN" \
  --arg task_definition "$TASK_DEFINITION" \
  --arg cluster_arn "$CLUSTER_ARN" \
  --arg stop_reason "$STOP_REASON" \
  --arg container_reason "$CONTAINER_REASON" \
  --argjson exit_code "$EXIT_CODE" \
  '{schema_version:1,deployment_id:$deployment_id,task_arn:$task_arn,task_definition:$task_definition,cluster_arn:$cluster_arn,exit_code:$exit_code,stop_reason:$stop_reason,container_reason:$container_reason,passed:($exit_code == 0)}' \
  > "$OUTPUT_JSON"

if [[ "$EXIT_CODE" != "0" ]]; then
  echo "migration task failed: exit=$EXIT_CODE stop=$STOP_REASON container=$CONTAINER_REASON" >&2
  exit 67
fi

echo "migration task succeeded: $TASK_ARN"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-database-bootstrap-dir> <release-git-sha> <output-json>" >&2
  exit 64
}

[[ $# -eq 3 ]] || usage
ROOT="$1"
RELEASE_GIT_SHA="$2"
OUTPUT_JSON="$3"

[[ "$RELEASE_GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid release git sha" >&2; exit 64; }
mkdir -p "$(dirname "$OUTPUT_JSON")"

TASK_DEFINITION="$(terraform -chdir="$ROOT" output -raw database_bootstrap_task_definition_arn)"
NETWORK_JSON="$(terraform -chdir="$ROOT" output -json database_bootstrap_network)"
LOG_GROUP="$(terraform -chdir="$ROOT" output -raw database_bootstrap_log_group_name)"
API_IMAGE="$(terraform -chdir="$ROOT" output -raw database_bootstrap_api_image)"
ROOT_RELEASE_SHA="$(terraform -chdir="$ROOT" output -raw database_bootstrap_release_git_sha)"
SECRET_ARNS="$(terraform -chdir="$ROOT" output -json database_role_secret_arns)"

[[ "$ROOT_RELEASE_SHA" = "$RELEASE_GIT_SHA" ]] || { echo "database bootstrap Terraform release SHA mismatch" >&2; exit 65; }
CLUSTER_ARN="$(jq -r '.cluster_arn' <<<"$NETWORK_JSON")"
SUBNETS_CSV="$(jq -r '.private_subnet_ids | join(",")' <<<"$NETWORK_JSON")"
SECURITY_GROUPS_CSV="$(jq -r '.security_group_ids | join(",")' <<<"$NETWORK_JSON")"

for value in "$TASK_DEFINITION" "$CLUSTER_ARN" "$SUBNETS_CSV" "$SECURITY_GROUPS_CSV" "$LOG_GROUP" "$API_IMAGE"; do
  [[ -n "$value" && "$value" != "null" ]] || { echo "database bootstrap execution metadata missing" >&2; exit 65; }
done
[[ "$(jq '.security_group_ids | length' <<<"$NETWORK_JSON")" -eq 2 ]] || { echo "database bootstrap must use exactly two security groups" >&2; exit 65; }

TASK_ARN="$(aws ecs run-task \
  --cluster "$CLUSTER_ARN" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEFINITION" \
  --started-by "lumi-db-bootstrap-${GITHUB_RUN_ID:-manual}" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS_CSV],securityGroups=[$SECURITY_GROUPS_CSV],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' \
  --output text)"

[[ -n "$TASK_ARN" && "$TASK_ARN" != "None" ]] || { echo "ECS did not return a database bootstrap task ARN" >&2; exit 66; }
aws ecs wait tasks-stopped --cluster "$CLUSTER_ARN" --tasks "$TASK_ARN"

DESCRIPTION="$(aws ecs describe-tasks --cluster "$CLUSTER_ARN" --tasks "$TASK_ARN")"
EXIT_CODE="$(jq -r '.tasks[0].containers[] | select(.name == "database-bootstrap") | .exitCode // -1' <<<"$DESCRIPTION")"
STOP_REASON="$(jq -r '.tasks[0].stoppedReason // "unknown"' <<<"$DESCRIPTION")"
CONTAINER_REASON="$(jq -r '.tasks[0].containers[] | select(.name == "database-bootstrap") | .reason // ""' <<<"$DESCRIPTION")"
TASK_ID="${TASK_ARN##*/}"
LOG_STREAM="database-bootstrap/database-bootstrap/${TASK_ID}"

LOG_EVENTS=''
for _attempt in $(seq 1 12); do
  if LOG_EVENTS="$(aws logs get-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --start-from-head \
    --output json 2>/dev/null)"; then
    if jq -e '.events | length > 0' >/dev/null <<<"$LOG_EVENTS"; then
      break
    fi
  fi
  sleep 5
done

EVIDENCE_LINE="$(jq -r '[.events[].message | select(startswith("LUMI_DB_IDENTITY_EVIDENCE="))] | last // empty' <<<"${LOG_EVENTS:-{\"events\":[]}}")"
EVIDENCE_JSON="${EVIDENCE_LINE#LUMI_DB_IDENTITY_EVIDENCE=}"

if [[ "$EXIT_CODE" != "0" ]]; then
  echo "database bootstrap task failed: exit=$EXIT_CODE stop=$STOP_REASON container=$CONTAINER_REASON" >&2
  exit 67
fi
[[ -n "$EVIDENCE_LINE" && "$EVIDENCE_LINE" != "$EVIDENCE_JSON" ]] || { echo "database bootstrap evidence marker missing" >&2; exit 68; }
jq -e --arg sha "$RELEASE_GIT_SHA" '
  .schema_version == 1 and
  .kind == "LUMI_STAGING_DATABASE_IDENTITY_BOOTSTRAP_V1" and
  .status == "PASS" and
  .release_git_sha == $sha and
  .roles.lumi_app.superuser == false and
  .roles.lumi_app.create_role == false and
  .roles.lumi_app.create_database == false and
  .roles.lumi_app.schema_create == false and
  .roles.lumi_app.create_probe_denied == true and
  .roles.lumi_migration.superuser == false and
  .roles.lumi_migration.create_role == false and
  .roles.lumi_migration.create_database == false and
  .roles.lumi_migration.schema_create == true and
  .roles.lumi_migration.create_probe_passed == true and
  .cross_membership.app_member_of_migration == false and
  .cross_membership.migration_member_of_app == false and
  .master_role_distinct == true and
  (.extensions | sort) == ["pgcrypto", "vector"]
' >/dev/null <<<"$EVIDENCE_JSON"

APP_SECRET_ARN="$(jq -r '.app' <<<"$SECRET_ARNS")"
MIGRATION_SECRET_ARN="$(jq -r '.migration' <<<"$SECRET_ARNS")"
for value in "$APP_SECRET_ARN" "$MIGRATION_SECRET_ARN"; do
  [[ "$value" == arn:aws:secretsmanager:* ]] || { echo "invalid database role secret ARN" >&2; exit 69; }
done

current_version_id() {
  local secret_arn="$1"
  aws secretsmanager list-secret-version-ids \
    --secret-id "$secret_arn" \
    --include-deprecated \
    --query 'Versions[?contains(VersionStages, `AWSCURRENT`)].VersionId | [0]' \
    --output text
}

APP_SECRET_VERSION="$(current_version_id "$APP_SECRET_ARN")"
MIGRATION_SECRET_VERSION="$(current_version_id "$MIGRATION_SECRET_ARN")"
for value in "$APP_SECRET_VERSION" "$MIGRATION_SECRET_VERSION"; do
  [[ -n "$value" && "$value" != "None" ]] || { echo "database role secret current version missing" >&2; exit 69; }
done

jq -n \
  --arg release_git_sha "$RELEASE_GIT_SHA" \
  --arg task_arn "$TASK_ARN" \
  --arg task_definition "$TASK_DEFINITION" \
  --arg cluster_arn "$CLUSTER_ARN" \
  --arg api_image "$API_IMAGE" \
  --arg log_group "$LOG_GROUP" \
  --arg log_stream "$LOG_STREAM" \
  --arg stop_reason "$STOP_REASON" \
  --arg container_reason "$CONTAINER_REASON" \
  --arg app_secret_arn "$APP_SECRET_ARN" \
  --arg app_secret_version "$APP_SECRET_VERSION" \
  --arg migration_secret_arn "$MIGRATION_SECRET_ARN" \
  --arg migration_secret_version "$MIGRATION_SECRET_VERSION" \
  --argjson exit_code "$EXIT_CODE" \
  --argjson database_evidence "$EVIDENCE_JSON" \
  '{schema_version:1,kind:"LUMI_STAGING_DATABASE_IDENTITY_RUN_V1",status:"PASS",release_git_sha:$release_git_sha,task:{arn:$task_arn,task_definition:$task_definition,cluster_arn:$cluster_arn,exit_code:$exit_code,stop_reason:$stop_reason,container_reason:$container_reason},runtime:{api_image:$api_image,log_group:$log_group,log_stream:$log_stream},secrets:{app:{arn:$app_secret_arn,current_version_id:$app_secret_version},migration:{arn:$migration_secret_arn,current_version_id:$migration_secret_version}},database_evidence:$database_evidence}' > "$OUTPUT_JSON"

python3 -m json.tool "$OUTPUT_JSON" >/dev/null
echo "database identity bootstrap succeeded: $TASK_ARN"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <terraform-app-dir> <deployment-manifest-json> <output-json>" >&2
  exit 64
}

[[ $# -eq 3 ]] || usage
APP_DIR="$1"
MANIFEST="$2"
OUTPUT_JSON="$3"
mkdir -p "$(dirname "$OUTPUT_JSON")"

[[ -f "$MANIFEST" ]] || { echo "deployment manifest missing" >&2; exit 64; }
DEPLOYMENT_ID="$(jq -r '.deployment_id // empty' "$MANIFEST")"
RC_SHA="$(jq -r '.release_candidate.git_sha // empty' "$MANIFEST")"
RC_VERSION="$(jq -r '.release_candidate.version // empty' "$MANIFEST")"
MIGRATION_HEAD="$(jq -r '.release_candidate.migration_head // empty' "$MANIFEST")"
EXPECTED_STRATEGY="$(jq -r '.rollout.public_api_strategy // empty' "$MANIFEST")"
EXPECTED_PERCENT="$(jq -r '.rollout.public_api_canary_percent // -1' "$MANIFEST")"
EXPECTED_BAKE="$(jq -r '.rollout.public_api_canary_bake_minutes // -1' "$MANIFEST")"
EXPECTED_ROLLBACK="$(jq -r '.rollout.public_api_alarm_rollback // false' "$MANIFEST")"

[[ "$EXPECTED_STRATEGY" == "ECS_CANARY" && "$EXPECTED_PERCENT" -eq 5 && "$EXPECTED_BAKE" -eq 10 && "$EXPECTED_ROLLBACK" == true ]] || {
  echo "manifest rollout is not the canonical NODE-72 policy" >&2
  exit 65
}

CLUSTER_ARN="$(terraform -chdir="$APP_DIR" output -raw cluster_arn)"
SERVICE="$(aws ecs describe-services --cluster "$CLUSTER_ARN" --services api)"
[[ "$(jq '.failures | length' <<<"$SERVICE")" -eq 0 ]] || { echo "ECS api describe failed" >&2; exit 66; }

CONFIG="$(jq -c '.services[0].deploymentConfiguration // {}' <<<"$SERVICE")"
STRATEGY="$(jq -r '.strategy // empty' <<<"$CONFIG")"
BAKE="$(jq -r '.bakeTimeInMinutes // -1' <<<"$CONFIG")"
CANARY_PERCENT="$(jq -r '.canaryConfiguration.canaryPercent // -1' <<<"$CONFIG")"
CANARY_BAKE="$(jq -r '.canaryConfiguration.canaryBakeTimeInMinutes // -1' <<<"$CONFIG")"
ALARMS_ENABLED="$(jq -r '.alarms.enable // false' <<<"$CONFIG")"
ALARMS_ROLLBACK="$(jq -r '.alarms.rollback // false' <<<"$CONFIG")"
mapfile -t ALARM_NAMES < <(jq -r '.alarms.alarmNames[]? // empty' <<<"$CONFIG")

[[ "$STRATEGY" == "CANARY" ]] || { echo "ECS api strategy is not CANARY" >&2; exit 67; }
[[ "$BAKE" -eq 10 && "$CANARY_PERCENT" -eq 5 && "$CANARY_BAKE" -eq 10 ]] || {
  echo "ECS api canary percentage/bake policy mismatch" >&2
  exit 67
}
[[ "$ALARMS_ENABLED" == true && "$ALARMS_ROLLBACK" == true ]] || {
  echo "ECS api alarm rollback is not enabled" >&2
  exit 67
}
[[ ${#ALARM_NAMES[@]} -ge 2 ]] || { echo "ECS api must reference canary rollback alarms" >&2; exit 67; }

LB="$(jq -c '.services[0].loadBalancers[0] // {}' <<<"$SERVICE")"
ALT_TG="$(jq -r '.advancedConfiguration.alternateTargetGroupArn // empty' <<<"$LB")"
LISTENER_RULE="$(jq -r '.advancedConfiguration.productionListenerRule // empty' <<<"$LB")"
[[ -n "$ALT_TG" && -n "$LISTENER_RULE" ]] || {
  echo "ECS api advanced blue/green target configuration missing" >&2
  exit 67
}

ALARMS="$(aws cloudwatch describe-alarms --alarm-names "${ALARM_NAMES[@]}")"
RETURNED="$(jq '.MetricAlarms | length' <<<"$ALARMS")"
[[ "$RETURNED" -eq ${#ALARM_NAMES[@]} ]] || { echo "not all ECS canary alarms resolved" >&2; exit 68; }
ALARM_ROWS="$(jq -c '[.MetricAlarms[] | {name:.AlarmName,state:.StateValue,reason:(.StateReason // null),updated_at:(.StateUpdatedTimestamp // null)}] | sort_by(.name)' <<<"$ALARMS")"
if jq -e 'any(.[]; .state == "ALARM")' <<<"$ALARM_ROWS" >/dev/null; then
  echo "one or more canary rollback alarms are currently ALARM" >&2
  exit 68
fi

jq -n \
  --arg deployment_id "$DEPLOYMENT_ID" \
  --arg git_sha "$RC_SHA" \
  --arg version "$RC_VERSION" \
  --arg migration_head "$MIGRATION_HEAD" \
  --arg cluster_arn "$CLUSTER_ARN" \
  --arg strategy "$STRATEGY" \
  --arg alternate_target_group_arn "$ALT_TG" \
  --arg production_listener_rule "$LISTENER_RULE" \
  --argjson canary_percent "$CANARY_PERCENT" \
  --argjson bake_time_minutes "$BAKE" \
  --argjson canary_bake_time_minutes "$CANARY_BAKE" \
  --argjson alarms "$ALARM_ROWS" \
  '{schema_version:1,deployment_id:$deployment_id,release_candidate:{git_sha:$git_sha,version:$version,migration_head:$migration_head},strategy:$strategy,canary_percent:$canary_percent,bake_time_minutes:$bake_time_minutes,canary_bake_time_minutes:$canary_bake_time_minutes,alarms_enabled:true,alarms_rollback:true,alternate_target_group_arn:$alternate_target_group_arn,production_listener_rule:$production_listener_rule,alarms:$alarms,passed:true}' \
  > "$OUTPUT_JSON"

echo "production rollout evidence: PASS"

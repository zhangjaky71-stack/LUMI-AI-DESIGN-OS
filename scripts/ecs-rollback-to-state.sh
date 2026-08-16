#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <known-good-ecs-state.json> <output-json>" >&2
  exit 64
}

[[ $# -eq 2 ]] || usage
STATE_FILE="$1"
OUTPUT_JSON="$2"
mkdir -p "$(dirname "$OUTPUT_JSON")"

for command in aws jq; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 65; }
done
[[ -f "$STATE_FILE" ]] || { echo "known-good state file missing: $STATE_FILE" >&2; exit 66; }

jq -e '
  .schema_version == 1 and
  .passed == true and
  (.cluster_arn | type == "string" and startswith("arn:")) and
  (.services | type == "array" and length > 0) and
  all(.services[];
    (.service_name | type == "string" and length > 0) and
    (.task_definition | type == "string" and contains(":task-definition/lumi-"))
  )
' "$STATE_FILE" >/dev/null || {
  echo "known-good ECS state is not a valid captured steady-state snapshot" >&2
  exit 67
}

CLUSTER_ARN="$(jq -r '.cluster_arn' "$STATE_FILE")"
mapfile -t SERVICES < <(jq -r '.services[].service_name' "$STATE_FILE")
[[ ${#SERVICES[@]} -gt 0 ]] || exit 67

BEFORE="$(aws ecs describe-services --cluster "$CLUSTER_ARN" --services "${SERVICES[@]}")"
[[ "$(jq '.failures | length' <<<"$BEFORE")" -eq 0 ]] || {
  echo "ECS describe-services returned failures before rollback" >&2
  exit 68
}

PLAN="$(jq -n --argjson current "$BEFORE" --slurpfile target "$STATE_FILE" '
  ($target[0].services | map({key:.service_name, value:.task_definition}) | from_entries) as $targets |
  [$current.services[] | {
    service_name: .serviceName,
    before_task_definition: .taskDefinition,
    target_task_definition: $targets[.serviceName]
  } | . + {requires_change: (.before_task_definition != .target_task_definition)}]
')"

if jq -e 'any(.[]; .target_task_definition == null)' <<<"$PLAN" >/dev/null; then
  echo "snapshot does not contain a rollback target for every live service" >&2
  exit 69
fi

CHANGED_COUNT="$(jq '[.[] | select(.requires_change)] | length' <<<"$PLAN")"
if [[ "$CHANGED_COUNT" -eq 0 && "${ALLOW_NOOP_ROLLBACK:-0}" != "1" ]]; then
  echo "rollback drill would be a no-op; a real post-promotion rollback must change at least one task definition" >&2
  exit 70
fi

# Validate all immutable targets before mutating any service.
while IFS= read -r target; do
  [[ -n "$target" ]] || continue
  STATUS="$(aws ecs describe-task-definition --task-definition "$target" --query 'taskDefinition.status' --output text)"
  [[ "$STATUS" == "ACTIVE" ]] || {
    echo "rollback target is not ACTIVE: $target" >&2
    exit 71
  }
done < <(jq -r '.[].target_task_definition' <<<"$PLAN" | sort -u)

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
while IFS= read -r encoded; do
  [[ -n "$encoded" ]] || continue
  ROW="$(printf '%s' "$encoded" | base64 --decode)"
  SERVICE="$(jq -r '.service_name' <<<"$ROW")"
  TARGET="$(jq -r '.target_task_definition' <<<"$ROW")"
  REQUIRES_CHANGE="$(jq -r '.requires_change' <<<"$ROW")"
  [[ "$REQUIRES_CHANGE" == "true" ]] || continue
  aws ecs update-service \
    --cluster "$CLUSTER_ARN" \
    --service "$SERVICE" \
    --task-definition "$TARGET" >/dev/null
done < <(jq -r '.[] | @base64' <<<"$PLAN")

aws ecs wait services-stable --cluster "$CLUSTER_ARN" --services "${SERVICES[@]}"
AFTER="$(aws ecs describe-services --cluster "$CLUSTER_ARN" --services "${SERVICES[@]}")"
[[ "$(jq '.failures | length' <<<"$AFTER")" -eq 0 ]] || {
  echo "ECS describe-services returned failures after rollback" >&2
  exit 72
}

RESULTS="$(jq -n --argjson plan "$PLAN" --argjson after "$AFTER" '
  ($after.services | map({key:.serviceName, value:{
    task_definition:.taskDefinition,
    status:.status,
    desired_count:.desiredCount,
    running_count:.runningCount,
    pending_count:.pendingCount,
    primary:([.deployments[] | select(.status == "PRIMARY")][0] // null)
  }}) | from_entries) as $actual |
  [$plan[] | . as $p | ($actual[.service_name]) as $a | {
    service_name: .service_name,
    before_task_definition: .before_task_definition,
    target_task_definition: .target_task_definition,
    after_task_definition: $a.task_definition,
    changed: .requires_change,
    steady: (
      $a.status == "ACTIVE" and
      $a.running_count == $a.desired_count and
      $a.pending_count == 0 and
      ($a.primary != null) and
      (($a.primary.rolloutState // "COMPLETED") == "COMPLETED")
    ),
    target_restored: ($a.task_definition == .target_task_definition)
  }]
')"

PASSED="$(jq 'all(.[]; .steady and .target_restored)' <<<"$RESULTS")"
COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

jq -n \
  --arg cluster_arn "$CLUSTER_ARN" \
  --arg source_snapshot "$STATE_FILE" \
  --arg started_at "$STARTED_AT" \
  --arg completed_at "$COMPLETED_AT" \
  --argjson changed_count "$CHANGED_COUNT" \
  --argjson passed "$PASSED" \
  --argjson services "$RESULTS" \
  '{
    schema_version: 1,
    passed: $passed,
    cluster_arn: $cluster_arn,
    source_snapshot: $source_snapshot,
    changed_service_count: $changed_count,
    database_downgrade_attempted: false,
    started_at: $started_at,
    completed_at: $completed_at,
    services: $services
  }' > "$OUTPUT_JSON"

if [[ "$PASSED" != "true" ]]; then
  echo "rollback did not restore every target task definition at steady state" >&2
  exit 73
fi

echo "ECS immutable task-definition rollback drill: PASS"

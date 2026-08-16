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

for command in aws terraform jq; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 65; }
done

TOPIC_ARN="$(terraform -chdir="$APP_DIR" output -raw deployment_alert_topic_arn)"
QUEUE_URL="$(terraform -chdir="$APP_DIR" output -raw deployment_alert_evidence_queue_url)"
[[ -n "$TOPIC_ARN" && "$TOPIC_ARN" != "null" ]] || { echo "deployment alert topic missing" >&2; exit 66; }
[[ -n "$QUEUE_URL" && "$QUEUE_URL" != "null" ]] || { echo "deployment alert evidence queue missing" >&2; exit 66; }

DRILL_ID="$(date -u +%Y%m%dT%H%M%SZ)-${GITHUB_RUN_ID:-local}-${RANDOM}"
ALARM_NAME="lumi-alert-delivery-drill-${DRILL_ID}"
NAMESPACE="LUMI/OperationalDrill"
METRIC_NAME="AlertDeliveryProbe"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ALARM_MESSAGE_ID=""
RECOVERY_MESSAGE_ID=""

cleanup() {
  aws cloudwatch delete-alarms --alarm-names "$ALARM_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_alarm_state() {
  local expected="$1"
  local deadline=$((SECONDS + 180))
  while (( SECONDS < deadline )); do
    local state
    state="$(aws cloudwatch describe-alarms --alarm-names "$ALARM_NAME" --query 'MetricAlarms[0].StateValue' --output text 2>/dev/null || true)"
    if [[ "$state" == "$expected" ]]; then
      return 0
    fi
    sleep 5
  done
  echo "alarm $ALARM_NAME did not reach $expected" >&2
  return 1
}

wait_delivery() {
  local expected="$1"
  local deadline=$((SECONDS + 180))
  while (( SECONDS < deadline )); do
    local batch
    batch="$(aws sqs receive-message \
      --queue-url "$QUEUE_URL" \
      --max-number-of-messages 10 \
      --wait-time-seconds 10 \
      --visibility-timeout 20 \
      --output json)"

    while IFS= read -r encoded; do
      [[ -n "$encoded" ]] || continue
      local row body notification alarm_name new_state receipt message_id
      row="$(printf '%s' "$encoded" | base64 --decode)"
      body="$(jq -r '.Body' <<<"$row")"
      receipt="$(jq -r '.ReceiptHandle' <<<"$row")"
      message_id="$(jq -r '.MessageId' <<<"$row")"
      notification="$(jq -r '.Message // empty' <<<"$body" 2>/dev/null || true)"
      [[ -n "$notification" ]] || continue
      alarm_name="$(jq -r '.AlarmName // empty' <<<"$notification" 2>/dev/null || true)"
      new_state="$(jq -r '.NewStateValue // empty' <<<"$notification" 2>/dev/null || true)"
      if [[ "$alarm_name" == "$ALARM_NAME" && "$new_state" == "$expected" ]]; then
        aws sqs delete-message --queue-url "$QUEUE_URL" --receipt-handle "$receipt" >/dev/null
        printf '%s' "$message_id"
        return 0
      fi
    done < <(jq -r '.Messages[]? | @base64' <<<"$batch")
  done
  echo "no SNS->SQS delivery observed for $ALARM_NAME state $expected" >&2
  return 1
}

aws cloudwatch put-metric-alarm \
  --alarm-name "$ALARM_NAME" \
  --alarm-description "Controlled LUMI alert delivery drill; safe synthetic metric only." \
  --actions-enabled \
  --alarm-actions "$TOPIC_ARN" \
  --ok-actions "$TOPIC_ARN" \
  --namespace "$NAMESPACE" \
  --metric-name "$METRIC_NAME" \
  --dimensions "Name=DrillId,Value=$DRILL_ID" \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --datapoints-to-alarm 1 \
  --period 10 \
  --statistic Maximum \
  --threshold 1 \
  --treat-missing-data notBreaching >/dev/null

# Establish a known healthy baseline before intentionally firing the alarm.
aws cloudwatch put-metric-data \
  --namespace "$NAMESPACE" \
  --metric-data "MetricName=$METRIC_NAME,Dimensions=[{Name=DrillId,Value=$DRILL_ID}],Value=0,Unit=Count,StorageResolution=1" >/dev/null
wait_alarm_state "OK"

# Fire one controlled alarm without touching application traffic or paid providers.
FIRED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
aws cloudwatch put-metric-data \
  --namespace "$NAMESPACE" \
  --metric-data "MetricName=$METRIC_NAME,Dimensions=[{Name=DrillId,Value=$DRILL_ID}],Value=1,Unit=Count,StorageResolution=1" >/dev/null
wait_alarm_state "ALARM"
ALARM_MESSAGE_ID="$(wait_delivery "ALARM")"

# Recover the signal and prove the OK notification is delivered through the same route.
RECOVERY_REQUESTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
aws cloudwatch put-metric-data \
  --namespace "$NAMESPACE" \
  --metric-data "MetricName=$METRIC_NAME,Dimensions=[{Name=DrillId,Value=$DRILL_ID}],Value=0,Unit=Count,StorageResolution=1" >/dev/null
wait_alarm_state "OK"
RECOVERY_MESSAGE_ID="$(wait_delivery "OK")"
COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

jq -n \
  --arg drill_id "$DRILL_ID" \
  --arg alarm_name "$ALARM_NAME" \
  --arg topic_arn "$TOPIC_ARN" \
  --arg queue_url "$QUEUE_URL" \
  --arg started_at "$STARTED_AT" \
  --arg fired_at "$FIRED_AT" \
  --arg alarm_message_id "$ALARM_MESSAGE_ID" \
  --arg recovery_requested_at "$RECOVERY_REQUESTED_AT" \
  --arg recovery_message_id "$RECOVERY_MESSAGE_ID" \
  --arg completed_at "$COMPLETED_AT" \
  '{
    schema_version: 1,
    drill_id: $drill_id,
    passed: true,
    alarm_name: $alarm_name,
    route: {
      cloudwatch_alarm: true,
      sns_topic_arn: $topic_arn,
      sqs_evidence_queue_url: $queue_url
    },
    transitions: [
      {state: "ALARM", requested_at: $fired_at, delivered_message_id: $alarm_message_id},
      {state: "OK", requested_at: $recovery_requested_at, delivered_message_id: $recovery_message_id}
    ],
    started_at: $started_at,
    completed_at: $completed_at
  }' > "$OUTPUT_JSON"

echo "Alert firing/recovery and SNS->SQS delivery drill: PASS"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <environment> <output-json>" >&2
  exit 64
}

[[ $# -eq 2 ]] || usage
ENVIRONMENT="$1"
OUTPUT_JSON="$2"
[[ "$ENVIRONMENT" == "staging" || "$ENVIRONMENT" == "production" ]] || usage
mkdir -p "$(dirname "$OUTPUT_JSON")"

required=(
  database/app
  database/migration
  redis/url
  rabbitmq/url
  providers/model
  providers/media
  billing/webhook
  auth/signing
)

results='[]'
failed=0
for purpose in "${required[@]}"; do
  secret_name="lumi-${ENVIRONMENT}/${purpose}"
  arn="$(aws secretsmanager describe-secret --secret-id "$secret_name" --query ARN --output text 2>/dev/null || true)"
  current="false"
  if [[ -n "$arn" && "$arn" != "None" ]]; then
    count="$(aws secretsmanager list-secret-version-ids --secret-id "$arn" --query 'length(Versions[?contains(VersionStages, `AWSCURRENT`)])' --output text 2>/dev/null || echo 0)"
    if [[ "$count" =~ ^[0-9]+$ && "$count" -ge 1 ]]; then current="true"; fi
  fi
  if [[ "$current" != "true" ]]; then failed=1; fi
  results="$(jq --arg purpose "$purpose" --arg arn "$arn" --argjson current "$current" '. + [{purpose:$purpose,arn:$arn,has_current_version:$current}]' <<<"$results")"
done

jq -n \
  --arg environment "$ENVIRONMENT" \
  --argjson results "$results" \
  --argjson passed "$([[ "$failed" -eq 0 ]] && echo true || echo false)" \
  '{schema_version:1,environment:$environment,passed:$passed,secrets:$results}' > "$OUTPUT_JSON"

if [[ "$failed" -ne 0 ]]; then
  echo "required ${ENVIRONMENT} Secret Manager values are missing AWSCURRENT versions" >&2
  exit 65
fi

echo "required ${ENVIRONMENT} secret versions are ready"

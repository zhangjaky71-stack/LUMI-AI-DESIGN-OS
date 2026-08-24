#!/usr/bin/env bash
set -euo pipefail

# LUMI AWS account bootstrap for AWS CloudShell.
#
# This script deliberately applies only the account bootstrap root from the
# already-hosted-validated release commit below. It does not deploy Staging or
# Production application resources.

BOOTSTRAP_REF="${LUMI_BOOTSTRAP_REF:-070315c2d3dd697bc87bc3a70acd7a3338175e40}"
TERRAFORM_VERSION="1.14.6"
REPOSITORY="zhangjaky71-stack/LUMI-AI-DESIGN-OS"
STATE_KEY="lumi/bootstrap/terraform.tfstate"
APPLY_TOKEN="APPLY_AWS_BOOTSTRAP"

fail() {
  printf 'LUMI AWS bootstrap failed: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is missing: $1"
}

need aws
need curl
need git
need python3
need sha256sum
need unzip

REGION="${LUMI_AWS_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-northeast-1}}}"
[[ "$REGION" =~ ^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$ ]] || fail "invalid AWS region: $REGION"

aws ec2 describe-regions \
  --region "$REGION" \
  --region-names "$REGION" \
  --query 'Regions[0].RegionName' \
  --output text >/tmp/lumi-bootstrap-region.txt
[[ "$(cat /tmp/lumi-bootstrap-region.txt)" == "$REGION" ]] || fail "AWS region is unavailable: $REGION"

aws sts get-caller-identity --output json >/tmp/lumi-bootstrap-caller.json
ACCOUNT_ID="$(python3 - <<'PY'
import json
p=json.load(open('/tmp/lumi-bootstrap-caller.json', encoding='utf-8'))
v=p.get('Account')
assert isinstance(v, str) and len(v) == 12 and v.isdigit(), p
print(v)
PY
)"
CALLER_ARN="$(python3 - <<'PY'
import json
p=json.load(open('/tmp/lumi-bootstrap-caller.json', encoding='utf-8'))
v=p.get('Arn')
assert isinstance(v, str) and v.startswith('arn:aws:'), p
print(v)
PY
)"
STATE_BUCKET="lumi-terraform-state-${ACCOUNT_ID}-${REGION}"
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

printf 'LUMI AWS bootstrap target\n'
printf '  account: %s\n' "$ACCOUNT_ID"
printf '  caller:  %s\n' "$CALLER_ARN"
printf '  region:  %s\n' "$REGION"
printf '  state:   %s\n' "$STATE_BUCKET"
printf '  source:  %s@%s\n' "$REPOSITORY" "$BOOTSTRAP_REF"

install_terraform() {
  local machine archive expected tmpdir
  machine="$(uname -m)"
  case "$machine" in
    x86_64|amd64)
      archive="terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
      expected="364c6ee08b0cb8fcbb28a115aacb2aa48e88abc56c149170bd65c2f75d98ea8d"
      ;;
    aarch64|arm64)
      archive="terraform_${TERRAFORM_VERSION}_linux_arm64.zip"
      expected="190037f64695556ac75965c00da5d85b3663f38553d909e9a51c4490cba4b6c1"
      ;;
    *)
      fail "unsupported CloudShell architecture: $machine"
      ;;
  esac

  if command -v terraform >/dev/null 2>&1 && [[ "$(terraform version -json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("terraform_version", ""))')" == "$TERRAFORM_VERSION" ]]; then
    return
  fi

  tmpdir="$(mktemp -d)"
  curl --fail --silent --show-error --location \
    "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/${archive}" \
    --output "${tmpdir}/${archive}"
  printf '%s  %s\n' "$expected" "${tmpdir}/${archive}" | sha256sum --check --status \
    || fail "Terraform ${TERRAFORM_VERSION} checksum verification failed"
  mkdir -p "$HOME/.local/bin"
  unzip -q -o "${tmpdir}/${archive}" -d "$HOME/.local/bin"
  export PATH="$HOME/.local/bin:$PATH"
  [[ "$(terraform version -json | python3 -c 'import json,sys; print(json.load(sys.stdin)["terraform_version"])')" == "$TERRAFORM_VERSION" ]] \
    || fail "unexpected Terraform version after install"
  rm -rf "$tmpdir"
}

install_terraform

WORKDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

git -C "$WORKDIR" init -q
git -C "$WORKDIR" remote add origin "https://github.com/${REPOSITORY}.git"
git -C "$WORKDIR" fetch -q --depth=1 origin "$BOOTSTRAP_REF"
git -C "$WORKDIR" checkout -q --detach FETCH_HEAD
[[ "$(git -C "$WORKDIR" rev-parse HEAD)" == "$BOOTSTRAP_REF" ]] || fail "bootstrap source SHA mismatch"

ROOT="$WORKDIR/infra/iac/bootstrap"
[[ -f "$ROOT/main.tf" && -f "$ROOT/variables.tf" && -f "$ROOT/versions.tf" ]] \
  || fail "bootstrap Terraform root is incomplete"

# Reuse the account-level GitHub provider if it already exists. If it does not,
# the validated Terraform bootstrap root creates it.
TF_ARGS=("-var=region=${REGION}")
if aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn "$OIDC_ARN" \
  >/tmp/lumi-bootstrap-existing-oidc.json 2>/tmp/lumi-bootstrap-existing-oidc.err; then
  TF_ARGS+=("-var=github_oidc_provider_arn=${OIDC_ARN}")
else
  if ! grep -Eq 'NoSuchEntity|not found|NoSuchEntityException' /tmp/lumi-bootstrap-existing-oidc.err; then
    cat /tmp/lumi-bootstrap-existing-oidc.err >&2
    fail "unable to determine whether the GitHub OIDC provider already exists"
  fi
fi

# Bootstrap state is intentionally local for the first creation. After a
# successful apply it is copied into the new encrypted/versioned state bucket.
# On a later CloudShell rerun, restore that exact state before planning.
if aws s3api head-bucket --bucket "$STATE_BUCKET" 2>/dev/null; then
  if aws s3api head-object \
    --bucket "$STATE_BUCKET" \
    --key "$STATE_KEY" \
    >/tmp/lumi-bootstrap-state-head.json 2>/dev/null; then
    aws s3 cp \
      "s3://${STATE_BUCKET}/${STATE_KEY}" \
      "$ROOT/terraform.tfstate" \
      --only-show-errors
    printf 'Restored existing encrypted bootstrap state.\n'
  else
    fail "derived state bucket already exists but has no ${STATE_KEY}; refusing an unaudited import/overwrite"
  fi
fi

terraform -chdir="$ROOT" init -backend=false -input=false
terraform -chdir="$ROOT" validate
terraform -chdir="$ROOT" plan \
  -input=false \
  -out=tfplan \
  "${TF_ARGS[@]}"
terraform -chdir="$ROOT" show -json tfplan >/tmp/lumi-bootstrap-plan.json

python3 - <<'PY'
import json
p=json.load(open('/tmp/lumi-bootstrap-plan.json', encoding='utf-8'))
bad=[]
counts={'create':0,'update':0,'delete':0,'replace':0,'no-op':0,'read':0}
for item in p.get('resource_changes', []):
    address=item.get('address','?')
    actions=item.get('change',{}).get('actions',[])
    if 'delete' in actions:
        bad.append((address, actions))
    if actions == ['create']:
        counts['create'] += 1
    elif actions == ['update']:
        counts['update'] += 1
    elif actions == ['delete']:
        counts['delete'] += 1
    elif 'delete' in actions and 'create' in actions:
        counts['replace'] += 1
    elif actions == ['no-op']:
        counts['no-op'] += 1
    elif actions == ['read']:
        counts['read'] += 1
if bad:
    raise SystemExit('bootstrap plan contains delete/replace actions: ' + repr(bad))
print('LUMI bootstrap plan safety summary:', json.dumps(counts, sort_keys=True))
PY

if [[ "${LUMI_BOOTSTRAP_APPLY:-}" != "$APPLY_TOKEN" ]]; then
  printf '\nPlan is safe but APPLY was not authorized.\n' >&2
  printf 'Run again with: LUMI_BOOTSTRAP_APPLY=%s\n' "$APPLY_TOKEN" >&2
  exit 65
fi

terraform -chdir="$ROOT" apply -input=false tfplan
terraform -chdir="$ROOT" output -json >/tmp/lumi-bootstrap-terraform-output.json

OUTPUT_STATE_BUCKET="$(python3 - <<'PY'
import json
p=json.load(open('/tmp/lumi-bootstrap-terraform-output.json', encoding='utf-8'))
print(p['state_bucket']['value'])
PY
)"
OUTPUT_KMS_KEY="$(python3 - <<'PY'
import json
p=json.load(open('/tmp/lumi-bootstrap-terraform-output.json', encoding='utf-8'))
print(p['state_kms_key_arn']['value'])
PY
)"
[[ "$OUTPUT_STATE_BUCKET" == "$STATE_BUCKET" ]] || fail "bootstrap state bucket output mismatch"
[[ "$OUTPUT_KMS_KEY" == arn:aws:kms:* ]] || fail "bootstrap KMS output is invalid"

aws s3 cp \
  "$ROOT/terraform.tfstate" \
  "s3://${STATE_BUCKET}/${STATE_KEY}" \
  --sse aws:kms \
  --sse-kms-key-id "$OUTPUT_KMS_KEY" \
  --only-show-errors
aws s3api head-object \
  --bucket "$STATE_BUCKET" \
  --key "$STATE_KEY" \
  >/tmp/lumi-bootstrap-state-head-after.json

# Query the real target Region rather than guessing service pins.
aws rds describe-db-engine-versions \
  --region "$REGION" \
  --engine postgres \
  --query 'DBEngineVersions[].EngineVersion' \
  --output json >/tmp/lumi-postgres-versions.json
aws elasticache describe-cache-engine-versions \
  --region "$REGION" \
  --engine redis \
  --query 'CacheEngineVersions[].EngineVersion' \
  --output json >/tmp/lumi-redis-versions.json
aws mq describe-broker-engine-types \
  --region "$REGION" \
  --engine-type RABBITMQ \
  --output json >/tmp/lumi-rabbitmq-engine-types.json
aws mq describe-broker-instance-options \
  --region "$REGION" \
  --engine-type RABBITMQ \
  --output json >/tmp/lumi-rabbitmq-instance-options.json

HANDOFF="$HOME/lumi-aws-bootstrap-handoff.json"
BOOTSTRAP_REF="$BOOTSTRAP_REF" \
REGION="$REGION" \
ACCOUNT_ID="$ACCOUNT_ID" \
CALLER_ARN="$CALLER_ARN" \
python3 - <<'PY' >"$HANDOFF"
import datetime
import json
import os

out=json.load(open('/tmp/lumi-bootstrap-terraform-output.json', encoding='utf-8'))
def value(name):
    return out[name]['value']

payload={
    'schema_version': 1,
    'kind': 'LUMI_AWS_RELEASE_BOOTSTRAP_HANDOFF_V1',
    'status': 'PASS',
    'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'bootstrap_source_sha': os.environ['BOOTSTRAP_REF'],
    'operator_identity': {
        'account_id': os.environ['ACCOUNT_ID'],
        'caller_arn': os.environ['CALLER_ARN'],
        'region': os.environ['REGION'],
    },
    'github_oidc_provider_arn': value('github_oidc_provider_arn'),
    'state_bucket': value('state_bucket'),
    'state_kms_key_arn': value('state_kms_key_arn'),
    'github_deploy_role_arns': value('github_deploy_role_arns'),
    'staging_environment_bootstrap': value('staging_environment_bootstrap'),
    'production_environment_bootstrap': value('production_environment_bootstrap'),
    'region_capability_candidates': {
        'postgres_engine_versions': json.load(open('/tmp/lumi-postgres-versions.json', encoding='utf-8')),
        'redis_engine_versions': json.load(open('/tmp/lumi-redis-versions.json', encoding='utf-8')),
        'rabbitmq_engine_types': json.load(open('/tmp/lumi-rabbitmq-engine-types.json', encoding='utf-8')),
        'rabbitmq_instance_options': json.load(open('/tmp/lumi-rabbitmq-instance-options.json', encoding='utf-8')),
    },
    'bootstrap_state': {
        'bucket': value('state_bucket'),
        'key': 'lumi/bootstrap/terraform.tfstate',
        'encrypted_with': value('state_kms_key_arn'),
    },
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY

printf '\nLUMI_AWS_BOOTSTRAP_OUTPUT_BEGIN\n'
cat "$HANDOFF"
printf 'LUMI_AWS_BOOTSTRAP_OUTPUT_END\n'
printf '\nBootstrap complete. Handoff file: %s\n' "$HANDOFF"
printf 'No Staging/Production application resources were deployed by this script.\n'

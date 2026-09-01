#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/aws_release_bootstrap_cloudshell.sh"
BOOTSTRAP_MAIN = ROOT / "infra/iac/bootstrap/main.tf"
BOOTSTRAP_VARIABLES = ROOT / "infra/iac/bootstrap/variables.tf"

EXPECTED_BOOTSTRAP_REF = "070315c2d3dd697bc87bc3a70acd7a3338175e40"
EXPECTED_TERRAFORM_VERSION = "1.14.6"
EXPECTED_TERRAFORM_SHA256 = {
    "linux_amd64": "364c6ee08b0cb8fcbb28a115aacb2aa48e88abc56c149170bd65c2f75d98ea8d",
    "linux_arm64": "190037f64695556ac75965c00da5d85b3663f38553d909e9a51c4490cba4b6c1",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"AWS release bootstrap contract invalid: {message}")


def terraform_resource_body(text: str, resource_type: str, name: str) -> str:
    header = f'resource "{resource_type}" "{name}" {{'
    start = text.find(header)
    require(start >= 0, f"missing Terraform resource {resource_type}.{name}")
    body_start = start + len(header)
    depth = 1
    index = body_start
    while index < len(text) and depth:
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    require(depth == 0, f"unterminated Terraform resource {resource_type}.{name}")
    return text[body_start : index - 1]


def require_order(text: str, markers: tuple[str, ...], message: str) -> None:
    positions = []
    for marker in markers:
        position = text.find(marker)
        require(position >= 0, f"{message}: missing marker {marker!r}")
        positions.append(position)
    require(positions == sorted(positions), message)


def python_heredoc_containing(text: str, marker: str) -> str:
    opener = "python3 - <<'PY'\n"
    terminator = "\nPY\n"
    search_from = 0
    while True:
        start = text.find(opener, search_from)
        require(start >= 0, f"missing Python heredoc containing {marker!r}")
        body_start = start + len(opener)
        body_end = text.find(terminator, body_start)
        require(body_end >= 0, "unterminated Python heredoc")
        body = text[body_start:body_end]
        if marker in body:
            return body
        search_from = body_end + len(terminator)


def _is_named_assignment(node: ast.AST, target_name: str, mapping_name: str, key: str) -> bool:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    target = node.targets[0]
    value = node.value
    return (
        isinstance(target, ast.Name)
        and target.id == target_name
        and isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == mapping_name
        and value.func.attr == "get"
        and len(value.args) == 1
        and isinstance(value.args[0], ast.Constant)
        and value.args[0].value == key
        and not value.keywords
    )


def require_existing_oidc_validation(block: str) -> None:
    tree = ast.parse(block)
    nodes = list(ast.walk(tree))

    require(
        any(_is_named_assignment(node, "url", "p", "Url") for node in nodes),
        "existing OIDC validation must read the issuer from the AWS Url field",
    )
    require(
        any(_is_named_assignment(node, "client_ids", "p", "ClientIDList") for node in nodes),
        "existing OIDC validation must read the AWS ClientIDList field",
    )

    expected_issuers = {
        "token.actions.githubusercontent.com",
        "https://token.actions.githubusercontent.com",
    }
    issuer_checks = []
    audience_checks = 0
    list_type_checks = 0

    for node in nodes:
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue

        comparator = node.comparators[0]
        if (
            isinstance(node.left, ast.Name)
            and node.left.id == "url"
            and isinstance(node.ops[0], ast.NotIn)
            and isinstance(comparator, ast.Set)
        ):
            values = {
                element.value
                for element in comparator.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
            if len(values) == len(comparator.elts):
                issuer_checks.append(values)

        if (
            isinstance(node.left, ast.Constant)
            and node.left.value == "sts.amazonaws.com"
            and isinstance(node.ops[0], ast.NotIn)
            and isinstance(comparator, ast.Name)
            and comparator.id == "client_ids"
        ):
            audience_checks += 1

    for node in nodes:
        if not isinstance(node, ast.UnaryOp) or not isinstance(node.op, ast.Not):
            continue
        operand = node.operand
        if not (
            isinstance(operand, ast.Call)
            and isinstance(operand.func, ast.Name)
            and operand.func.id == "isinstance"
            and len(operand.args) == 2
        ):
            continue
        value, expected_type = operand.args
        if (
            isinstance(value, ast.Name)
            and value.id == "client_ids"
            and isinstance(expected_type, ast.Name)
            and expected_type.id == "list"
        ):
            list_type_checks += 1

    require(
        issuer_checks == [expected_issuers],
        "existing OIDC issuer validation must use only the canonical GitHub Actions issuer forms",
    )
    require(
        audience_checks == 1 and list_type_checks == 1,
        "existing OIDC audience validation must require a ClientIDList containing the exact AWS STS audience",
    )


def main() -> int:
    require(SCRIPT.is_file(), "missing CloudShell bootstrap script")
    require(BOOTSTRAP_MAIN.is_file(), "missing bootstrap main.tf")
    require(BOOTSTRAP_VARIABLES.is_file(), "missing bootstrap variables.tf")

    script = SCRIPT.read_text(encoding="utf-8")
    main_tf = BOOTSTRAP_MAIN.read_text(encoding="utf-8")
    variables_tf = BOOTSTRAP_VARIABLES.read_text(encoding="utf-8")

    require(
        f'BOOTSTRAP_REF="{EXPECTED_BOOTSTRAP_REF}"' in script,
        "CloudShell bootstrap source SHA is not exactly pinned to the hosted-validated bootstrap",
    )
    require(
        "LUMI_BOOTSTRAP_REF" not in script,
        "bootstrap source SHA must not be runtime-overridable",
    )
    require(
        f'TERRAFORM_VERSION="{EXPECTED_TERRAFORM_VERSION}"' in script,
        "Terraform CLI version is not exactly pinned",
    )
    for arch, checksum in EXPECTED_TERRAFORM_SHA256.items():
        require(checksum in script, f"missing pinned Terraform SHA-256 for {arch}")
    require("sha256sum --check --status" in script, "Terraform archive checksum is not enforced")
    require(
        "https://releases.hashicorp.com/terraform/" in script,
        "Terraform download is not bound to HashiCorp releases",
    )

    require("aws sts get-caller-identity" in script, "AWS caller identity preflight is missing")
    require("aws ec2 describe-regions" in script, "AWS Region preflight is missing")
    require(
        'git -C "$WORKDIR" checkout -q --detach FETCH_HEAD' in script,
        "bootstrap source checkout is not detached",
    )
    require(
        '[[ "$(git -C "$WORKDIR" rev-parse HEAD)" == "$BOOTSTRAP_REF" ]]' in script,
        "bootstrap source SHA equality check is missing",
    )

    require('RECOVERY_STATE="$HOME/lumi-aws-bootstrap-recovery.tfstate"' in script, "local bootstrap recovery state is missing")
    require("REMOTE_STATE_EXISTS=0" in script, "remote-state existence classification is missing")
    require("OIDC_MANAGED_BY_STATE=0" in script, "OIDC Terraform-ownership classification is missing")
    require(
        "aws_iam_openid_connect_provider.github[0]" in script,
        "Terraform-managed OIDC state address is not inspected",
    )
    require_order(
        script,
        (
            "# Restore state before deciding OIDC ownership.",
            'terraform -chdir="$ROOT" init -backend=false -input=false',
            "OIDC_MANAGED_BY_STATE=0",
            "aws iam get-open-id-connect-provider",
            'TF_ARGS=("-var=region=${REGION}")',
        ),
        "bootstrap must restore/init/inspect state before deciding OIDC reuse",
    )
    require(
        "Never convert a Terraform-managed provider into an external input on rerun." in script,
        "Terraform-owned OIDC rerun invariant is missing",
    )
    require(
        "externally pre-existing provider; reusing validated ARN" in script,
        "external OIDC reuse path is missing",
    )
    oidc_validation = python_heredoc_containing(
        script,
        "lumi-bootstrap-existing-oidc.json",
    )
    require_existing_oidc_validation(oidc_validation)

    require("BUCKET_EXISTS=0" in script, "state bucket existence classification is missing")
    require(
        "refusing a possible foreign bucket collision" in script,
        "foreign state-bucket collision must fail closed",
    )
    require(
        "local recovery state diverges from remote bootstrap state" in script,
        "remote/local state divergence must fail closed",
    )
    require(
        "refusing an unaudited import/overwrite" in script,
        "pre-existing bucket without trusted state must fail closed",
    )

    require('terraform -chdir="$ROOT" plan' in script, "bootstrap Terraform plan is missing")
    require(
        'terraform -chdir="$ROOT" show -json tfplan' in script,
        "machine-readable plan inspection is missing",
    )
    require("if 'delete' in actions:" in script, "delete/replace plan rejection is missing")
    require(
        "bootstrap plan contains delete/replace actions" in script,
        "delete/replace plan failure is not explicit",
    )
    require('APPLY_TOKEN="APPLY_AWS_BOOTSTRAP"' in script, "explicit bootstrap apply token is missing")
    require(
        '"${LUMI_BOOTSTRAP_APPLY:-}" != "$APPLY_TOKEN"' in script,
        "bootstrap apply is not gated by explicit acknowledgement",
    )
    require(
        'terraform -chdir="$ROOT" apply -input=false tfplan' in script,
        "apply does not consume the reviewed plan",
    )

    require('STATE_KEY="lumi/bootstrap/terraform.tfstate"' in script, "bootstrap state key is not fixed")
    require("--sse aws:kms" in script, "bootstrap state upload does not require KMS encryption")
    require("--sse-kms-key-id" in script, "bootstrap state upload is not bound to the created KMS key")
    require(
        'cp "$ROOT/terraform.tfstate" "$RECOVERY_STATE"' in script
        and 'chmod 600 "$RECOVERY_STATE"' in script,
        "post-apply local recovery state is not persisted securely before upload",
    )
    require(
        'cmp -s "$RECOVERY_STATE" /tmp/lumi-bootstrap-state-verify.tfstate' in script,
        "remote state is not independently compared with the post-apply recovery state",
    )
    require(
        "Remote encrypted bootstrap state verified; local recovery copy removed." in script,
        "recovery state removal is not bound to remote verification",
    )
    apply_pos = script.find('terraform -chdir="$ROOT" apply -input=false tfplan')
    recovery_pos = script.find('cp "$ROOT/terraform.tfstate" "$RECOVERY_STATE"', apply_pos)
    upload_pos = script.find(
        'aws s3 cp \\\n  "$RECOVERY_STATE" \\\n  "s3://${STATE_BUCKET}/${STATE_KEY}"',
        recovery_pos,
    )
    verify_pos = script.find('/tmp/lumi-bootstrap-state-verify.tfstate', upload_pos)
    remove_pos = script.find('rm -f "$RECOVERY_STATE"', verify_pos)
    require(
        min(apply_pos, recovery_pos, upload_pos, verify_pos, remove_pos) >= 0
        and apply_pos < recovery_pos < upload_pos < verify_pos < remove_pos,
        "post-apply recovery state must precede remote upload/verification/removal",
    )
    require(
        "ServerSideEncryption" in script and "SSEKMSKeyId" in script,
        "remote bootstrap state KMS metadata is not verified",
    )

    for marker in (
        "aws rds describe-db-engine-versions",
        "aws elasticache describe-cache-engine-versions",
        "aws mq describe-broker-engine-types",
        "aws mq describe-broker-instance-options",
    ):
        require(marker in script, f"real Region capability query missing: {marker}")
    require("lumi-aws-bootstrap-handoff.json" in script, "bootstrap handoff artifact is missing")
    require("LUMI_AWS_RELEASE_BOOTSTRAP_HANDOFF_V2" in script, "bootstrap handoff V2 schema is missing")
    require("'remote_verified': True" in script, "handoff does not attest remote-state verification")
    require(
        "No Staging/Production application resources were deployed" in script,
        "bootstrap scope declaration is missing",
    )

    forbidden_script_markers = (
        "git push",
        "gh api",
        "gh variable",
        "gh secret",
        "aws s3 rm",
        "aws s3api delete-",
        "aws iam delete-",
        "aws kms schedule-key-deletion",
    )
    for marker in forbidden_script_markers:
        require(marker not in script, f"forbidden bootstrap side effect detected: {marker}")

    oidc_body = terraform_resource_body(main_tf, "aws_iam_openid_connect_provider", "github")
    oidc_urls = re.findall(r'^\s*url\s*=\s*"([^"]+)"\s*$', oidc_body, flags=re.MULTILINE)
    require(
        oidc_urls == ["https://token.actions.githubusercontent.com"],
        "GitHub OIDC provider URL must be exactly the canonical HTTPS issuer",
    )
    client_id_block = re.search(
        r"^\s*client_id_list\s*=\s*\[(.*?)^\s*\]\s*$",
        oidc_body,
        flags=re.MULTILINE | re.DOTALL,
    )
    require(client_id_block is not None, "GitHub OIDC client_id_list is missing")
    client_ids = re.findall(r'"([^"]+)"', client_id_block.group(1))
    require(
        client_ids == ["sts.amazonaws.com"],
        "GitHub OIDC audience must be exactly the AWS STS audience",
    )
    require(
        "environment:staging" in main_tf and "environment:production" in main_tf,
        "environment-scoped OIDC subjects are missing",
    )
    require("enable_key_rotation     = true" in main_tf, "Terraform-state KMS key rotation is not enabled")
    require("BucketOwnerEnforced" in main_tf, "Terraform-state bucket ownership enforcement is missing")
    require("block_public_acls       = true" in main_tf, "Terraform-state public ACL block is missing")
    require(
        "restrict_public_buckets = true" in main_tf,
        "Terraform-state public bucket restriction is missing",
    )
    require('status = "Enabled"' in main_tf, "Terraform-state versioning is not enabled")
    require(
        'sse_algorithm     = "aws:kms"' in main_tf,
        "Terraform-state bucket does not require KMS encryption",
    )
    require("aws:SecureTransport" in main_tf, "Terraform-state TLS-only bucket policy is missing")

    require('default     = null' in variables_tf, "optional bootstrap inputs are not nullable/defaulted")
    require(
        re.search(
            r'variable "github_oidc_provider_arn"[\s\S]+?default\s*=\s*null',
            variables_tf,
        )
        is not None,
        "existing GitHub OIDC provider reuse is not optional",
    )
    require(
        re.search(
            r'variable "state_bucket_name"[\s\S]+?default\s*=\s*null',
            variables_tf,
        )
        is not None,
        "state bucket name is not auto-derivable",
    )

    print("AWS release bootstrap contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

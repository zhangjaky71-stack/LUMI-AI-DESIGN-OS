#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/staging-database-identity-bootstrap.yml"
BRIDGE = ROOT / ".github/workflows/release-staging-database-identity-bridge.yml"
PREFLIGHT = ROOT / "scripts/validate_staging_database_bootstrap_preflight.py"
RUNNER = ROOT / "scripts/ecs-run-database-bootstrap-task.sh"
TF_ROOT = ROOT / "infra/iac/environments/staging/database-bootstrap"


class ContractError(RuntimeError):
    pass


def require(text: str, token: str, label: str) -> None:
    if token not in text:
        raise ContractError(f"missing {label}: {token!r}")


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise ContractError(f"forbidden {label}: {token!r}")


def main() -> int:
    for path in (WORKFLOW, BRIDGE, PREFLIGHT, RUNNER):
        if not path.is_file():
            raise ContractError(f"required file is missing: {path.relative_to(ROOT)}")
    for name in ("main.tf", "outputs.tf", "variables.tf", "versions.tf"):
        path = TF_ROOT / name
        if not path.is_file():
            raise ContractError(f"database-bootstrap Terraform file is missing: {path.relative_to(ROOT)}")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    tf_main = (TF_ROOT / "main.tf").read_text(encoding="utf-8")

    for operation in (
        "plan-database-bootstrap",
        "apply-database-bootstrap",
        "run-database-bootstrap",
    ):
        require(workflow, operation, "workflow operation")
        require(bridge, operation, "bridge operation")
        require(preflight, operation, "preflight operation")

    require(workflow, "environment: staging", "Staging environment boundary")
    require(workflow, "id-token: write", "OIDC permission")
    require(workflow, "contents: read", "read-only contents permission")
    forbid(workflow, "contents: write", "contents write permission")
    require(workflow, "APPLY_STAGING_DATABASE_BOOTSTRAP", "mutation acknowledgement")
    require(workflow, "lumi/staging/database-bootstrap/terraform.tfstate", "isolated state key")
    require(workflow, "TF_VAR_release_git_sha", "release SHA Terraform binding")
    require(workflow, "TF_VAR_api_image", "immutable API image Terraform binding")
    require(workflow, "TF_VAR_credential_generation", "credential generation binding")
    require(workflow, "promoted_image_set_json must contain exactly the six runtime services", "six-image set gate")
    require(workflow, "scripts/ecs-run-database-bootstrap-task.sh", "private one-shot runner")
    require(workflow, "LUMI_STAGING_DATABASE_IDENTITY_RUN_V1", "run evidence contract")
    require(
        workflow,
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
        "immutable evidence upload pin",
    )
    require(workflow, "retention-days: 180", "evidence retention")

    require(bridge, "production/staging/database-bootstrap-request-v1.json", "audited request path")
    require(bridge, "source_parent", "parent binding")
    require(bridge, "return_run_details", "dispatch run identity")
    require(bridge, "staging-database-identity-bootstrap.yml/dispatches", "canonical dispatch target")
    require(bridge, "mutation_ack=APPLY_STAGING_DATABASE_BOOTSTRAP", "bridge mutation acknowledgement")
    forbid(bridge, "environment: staging", "bridge AWS environment access")
    forbid(bridge, "id-token: write", "bridge OIDC access")

    # Secret names are defined at the Terraform ownership boundary. The runner
    # intentionally receives only Terraform's typed app/migration ARN map and
    # must never retrieve secret values on the GitHub-hosted runner.
    require(tf_main, 'secret_key = "database/app"', "App secret boundary")
    require(tf_main, 'secret_key = "database/migration"', "migration secret boundary")
    require(tf_main, 'local.core.secret_arns["database/app"]', "App secret binding")
    require(tf_main, 'local.core.secret_arns["database/migration"]', "migration secret binding")

    require(runner, "assignPublicIp=DISABLED", "private task networking")
    require(runner, "LUMI_STAGING_DATABASE_IDENTITY_BOOTSTRAP_V1", "inner database evidence")
    require(runner, "master_role_distinct == true", "master/runtime role separation")
    require(runner, 'APP_SECRET_ARN="$(jq -r \'.app\'', "App secret ARN handoff")
    require(runner, 'MIGRATION_SECRET_ARN="$(jq -r \'.migration\'', "migration secret ARN handoff")
    require(runner, "secrets:{app:{arn:$app_secret_arn", "App secret evidence")
    require(runner, "migration:{arn:$migration_secret_arn", "migration secret evidence")
    forbid(runner, "get-secret-value", "GitHub-runner secret value retrieval")

    print("staging database identity workflow contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

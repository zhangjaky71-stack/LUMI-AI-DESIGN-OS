from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _resource_block(source: str, resource_type: str, name: str) -> str:
    marker = f'resource "{resource_type}" "{name}" {{'
    start = source.index(marker)
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated Terraform resource: {resource_type}.{name}")


def test_sandbox_runtime_is_forced_onto_restricted_egress() -> None:
    compute = _read("infra/iac/modules/compute/main.tf")
    variables = _read("infra/iac/modules/compute/variables.tf")

    assert 'name == "sandbox-runtime"' in compute
    assert "[var.app_security_group_id, var.sandbox_egress_security_group_id]" in compute
    assert "[var.app_security_group_id, var.app_internet_egress_security_group_id]" in compute
    assert "security_groups  = local.service_security_groups[each.key]" in compute
    assert 'contains(keys(var.services), "sandbox-runtime")' in variables


def test_app_identity_group_does_not_grant_public_egress() -> None:
    network = _read("infra/iac/modules/network/main.tf")
    app = _resource_block(network, "aws_security_group", "app")
    internet = _resource_block(network, "aws_security_group", "app_internet_egress")

    assert 'cidr_blocks = ["0.0.0.0/0"]' not in app
    assert 'cidr_blocks = ["0.0.0.0/0"]' in internet


def test_sandbox_egress_has_no_arbitrary_public_destination() -> None:
    network = _read("infra/iac/modules/network/main.tf")
    sandbox = _resource_block(network, "aws_security_group", "sandbox_egress")

    assert 'cidr_blocks = ["0.0.0.0/0"]' not in sandbox
    assert "cidr_blocks = [aws_vpc.this.cidr_block]" in sandbox
    assert "prefix_list_ids = [data.aws_prefix_list.s3.id]" in sandbox
    assert 'EgressPolicy     = "deny-public-except-s3"' in sandbox


def test_sandbox_fargate_dependencies_use_private_aws_endpoints() -> None:
    network = _read("infra/iac/modules/network/main.tf")
    endpoint = _resource_block(network, "aws_vpc_endpoint", "runtime_interface")

    for service in ("ecr.api", "ecr.dkr", "logs", "secretsmanager"):
        assert f'"{service}"' in endpoint
    assert 'vpc_endpoint_type   = "Interface"' in endpoint
    assert "private_dns_enabled = true" in endpoint


def test_production_and_staging_propagate_restricted_egress_ids() -> None:
    for environment in ("production", "staging"):
        core = _read(f"infra/iac/environments/{environment}/core/outputs.tf")
        app = _read(f"infra/iac/environments/{environment}/app/main.tf")
        assert 'output "sandbox_egress_security_group_id"' in core
        assert 'output "app_internet_egress_security_group_id"' in core
        assert (
            "sandbox_egress_security_group_id       = "
            "local.core.sandbox_egress_security_group_id"
        ) in app
        assert (
            "app_internet_egress_security_group_id = "
            "local.core.app_internet_egress_security_group_id"
        ) in app


def test_inner_sandbox_execution_remains_network_none() -> None:
    backend = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/local_backend.py")
    assert '"--network",' in backend
    assert '"none",' in backend


def test_provider_cost_guard_default_is_fail_closed_and_capped() -> None:
    migration = _read("db/migrations/0015_provider_cost_guard.sql")
    snapshot_fix = _read("db/migrations/0016_provider_cost_guard_snapshot_fix.sql")

    assert "100.00000000" in migration
    assert "fail_closed boolean NOT NULL DEFAULT true" in migration
    assert "FOR UPDATE" in migration
    assert "COST_DAILY_CAP_EXCEEDED" in migration
    assert "PROVIDER_COST_LEDGER_APPEND_ONLY" in migration
    assert "v_day_cap" in snapshot_fix
    assert "v_committed + v_reserved + p_estimated_amount_usd > v_day_cap" in snapshot_fix

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _resource_block(source: str, resource_type: str, name: str) -> str:
    return _hcl_block(source, f'resource "{resource_type}" "{name}" {{')


def _hcl_block(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated HCL block: {marker}")


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


def test_provider_cost_guard_uses_canonical_node27_ledger() -> None:
    migration = _read(
        "apps/api/alembic/versions/0018_platform_provider_cost_guard.py"
    )
    guard = _read("apps/api/src/lumi_api/costs/platform_guard.py")
    adapter = _read("apps/api/src/lumi_api/costs/model_gateway_adapter.py")

    assert "100.00000000" in migration
    assert "daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000" in migration
    assert "fail_closed boolean NOT NULL DEFAULT true" in migration
    assert "REVOKE INSERT, UPDATE, DELETE" in migration
    assert "FROM platform_provider_cost_guard" in guard
    assert "cost_basis='provider_cost'" in guard
    assert "FROM cost_ledger" in guard
    assert "FROM cost_reservations" in guard
    assert "pg_advisory_xact_lock" in guard
    assert "cost-budget:platform:provider-usd:utc-day" in guard
    assert "PlatformGuardedCostGateway" in adapter
    assert "self.gateway = PlatformGuardedCostGateway(dsn)" in adapter


def test_hosted_model_gateway_cannot_fall_back_to_request_local_budget() -> None:
    path = ROOT / "apps/api/src/lumi_api/model_gateway_runtime.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    factory = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "build_hosted_model_gateway"
    )
    parameter_names = {
        item.arg
        for item in [
            *factory.args.posonlyargs,
            *factory.args.args,
            *factory.args.kwonlyargs,
        ]
    }

    assert "budget_guard" not in parameter_names
    assert "PostgresModelCostAccounting(database_dsn)" in source
    assert "LedgerBudgetGuard(accounting)" in source
    assert "budget_guard=budget_guard" in source
    assert "RequestBudgetGuard" not in source


def test_provider_credentials_only_reach_model_gateway() -> None:
    provider_keys = (
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
    )
    for environment in ("staging", "production"):
        source = _read(f"infra/iac/environments/{environment}/app/main.tf")
        gateway = _hcl_block(source, "model-gateway = {")
        assert 'LUMI_DATABASE_URL          = local.secret_arns["database/app"]' in gateway
        assert 'LUMI_MODEL_PROVIDER_SECRET = local.secret_arns["providers/model"]' in gateway
        assert 'LUMI_MEDIA_PROVIDER_SECRET = local.secret_arns["providers/media"]' in gateway

        for service in (
            "api",
            "agent-runtime",
            "tool-gateway",
            "worker-media",
            "sandbox-runtime",
        ):
            block = _hcl_block(source, f"{service} = {{")
            for key in provider_keys:
                assert key not in block, f"{environment}/{service} received {key}"


def test_release_closure_does_not_create_second_provider_ledger() -> None:
    assert not (ROOT / "db/migrations/0015_provider_cost_guard.sql").exists()
    assert not (ROOT / "db/migrations/0016_provider_cost_guard_snapshot_fix.sql").exists()
    assert not (
        ROOT
        / "services/model-gateway/src/lumi_model_gateway/postgres_cost_accounting.py"
    ).exists()

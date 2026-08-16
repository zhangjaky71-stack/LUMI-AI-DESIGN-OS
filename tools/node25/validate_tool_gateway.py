from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = ROOT / "services/tool-gateway/src/lumi_tool_gateway"
EXPECTED_RISKS = {
    "READ_INTERNAL",
    "READ_EXTERNAL",
    "WRITE_INTERNAL",
    "WRITE_EXTERNAL",
    "DESTRUCTIVE",
    "FINANCIAL",
    "PRIVILEGED",
}
EXPECTED_TOOLS = {
    "web.search",
    "web.fetch",
    "asset.read",
    "asset.write-derived",
    "project.query",
    "artifact.query",
    "sandbox.execute",
    "media.inspect",
}
EXPECTED_GAPS = {
    "TOOL-COMPOSITION-001",
    "TOOL-WEB-002",
    "TOOL-APPROVAL-003",
    "TOOL-MCP-004",
    "TOOL-AUDIT-005",
    "TOOL-NATIVE-006",
    "TOOL-CI-007",
}
FORBIDDEN_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "boto3",
    "docker",
    "subprocess",
}
FORBIDDEN_AUTHORITY_MARKERS = {
    "/var/run/docker.sock",
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
}


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require_python_parses() -> None:
    paths = [*TOOL_ROOT.rglob("*.py")]
    paths += list((ROOT / "services/tool-gateway/tests").glob("test_*.py"))
    paths += list((ROOT / "tools/node25").glob("*.py"))
    paths += [
        ROOT / "scripts/validate_tool_gateway_contract.py",
        ROOT / "scripts/integration_tool_gateway.py",
    ]
    for path in sorted(set(paths)):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def require_contracts() -> None:
    from lumi_tool_gateway.catalog import p0_tool_definitions
    from lumi_tool_gateway.contracts import ToolIdempotency, ToolRisk

    risks = {item.value for item in ToolRisk}
    if risks != EXPECTED_RISKS:
        raise AssertionError(f"ToolRisk drifted: {sorted(risks)}")
    definitions = p0_tool_definitions()
    names = {item.name for item in definitions}
    if names != EXPECTED_TOOLS or len(definitions) != len(EXPECTED_TOOLS):
        raise AssertionError(f"P0 Tool catalog drifted: {sorted(names)}")
    if any("sql" in item.name.casefold() for item in definitions):
        raise AssertionError("unrestricted SQL tool entered P0 catalog")
    for definition in definitions:
        if definition.is_write:
            if definition.idempotency is not ToolIdempotency.REQUIRED:
                raise AssertionError(f"write bypasses idempotency: {definition.key}")
            if len(definition.operation_type) > 100:
                raise AssertionError(f"NODE-20 operation type overflow: {definition.key}")


def require_default_deny_and_hitl() -> None:
    policy = read("services/tool-gateway/src/lumi_tool_gateway/policy.py")
    for marker in (
        "AGENT_TOOL_NOT_ALLOWED",
        "SUBAGENT_PERMISSION_ESCALATION",
        "ORG_TOOL_DENIED",
        "context.parent_allow_patterns is not None",
        "ToolRisk.WRITE_EXTERNAL",
        "ToolRisk.DESTRUCTIVE",
        "ToolRisk.FINANCIAL",
        "ToolRisk.PRIVILEGED",
    ):
        if marker not in policy:
            raise AssertionError(f"permission/HITL marker missing: {marker}")


def require_side_effect_and_audit_boundary() -> None:
    contracts = read("services/tool-gateway/src/lumi_tool_gateway/contracts.py")
    gateway = read("services/tool-gateway/src/lumi_tool_gateway/gateway.py")
    errors = read("services/tool-gateway/src/lumi_tool_gateway/errors.py")
    for marker in (
        "_MAX_IDEMPOTENCY_KEY_LENGTH = 255",
        "_MAX_OPERATION_TYPE_LENGTH = 100",
        "TOOL_WRITE_IDEMPOTENCY_REQUIRED",
        "def operation_type",
    ):
        if marker not in contracts:
            raise AssertionError(f"NODE-20 compatibility marker missing: {marker}")
    for marker in (
        "ToolAuditSinkRequiredError",
        "definition.is_write and not self._audit_enabled",
        "side_effect_guard.execute",
        "definition.operation_type",
        "validate_output",
        "result_offloader.store",
    ):
        if marker not in gateway:
            raise AssertionError(f"Gateway safety marker missing: {marker}")
    if "TOOL_IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST" not in errors:
        raise AssertionError("Tool idempotency conflict code missing")
    bridge = read("tools/node25/test_node20_side_effect_bridge.py")
    for marker in (
        "SideEffectGateway",
        "MemoryIdempotencyStore",
        "canonical_request_hash",
        "SideEffectKind.EXTERNAL_TOOL_WRITE",
        "ToolIdempotencyConflictError",
    ):
        if marker not in bridge:
            raise AssertionError(f"NODE-20 bridge marker missing: {marker}")


def require_ssrf_boundary() -> None:
    ssrf = read("services/tool-gateway/src/lumi_tool_gateway/ssrf.py")
    native = read("services/tool-gateway/src/lumi_tool_gateway/native.py")
    for marker in (
        'scheme not in {"http", "https"}',
        "host.docker.internal",
        "metadata.google.internal",
        "not ip.is_private",
        "not ip.is_link_local",
        "pinned_ip",
    ):
        if marker not in ssrf:
            raise AssertionError(f"SSRF marker missing: {marker}")
    for marker in (
        "resolved_ip=target.pinned_ip",
        "self.ssrf_policy.validate(current_url)",
        "current_url = urljoin",
    ):
        if marker not in native:
            raise AssertionError(f"fetch transport marker missing: {marker}")
    for forbidden in ('"Authorization"', '"Cookie"', "shell=True", "Popen("):
        if forbidden in native:
            raise AssertionError(f"ambient fetch/shell authority found: {forbidden}")


def require_no_ambient_authority() -> None:
    for path in TOOL_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = roots & FORBIDDEN_IMPORTS
                if bad:
                    raise AssertionError(f"{path}: forbidden imports {sorted(bad)}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    raise AssertionError(f"{path}: forbidden import {root}")
        for marker in FORBIDDEN_AUTHORITY_MARKERS:
            if marker in text:
                raise AssertionError(f"{path}: ambient authority marker {marker}")
    project = read("services/tool-gateway/pyproject.toml")
    if "dependencies = []" not in project:
        raise AssertionError("Tool Gateway core gained a direct dependency")


def require_gap_ledger() -> None:
    payload = json.loads(read("reports/nodes/NODE-25/gap-ledger.json"))
    ids = {item["id"] for item in payload["gaps"]}
    if ids != EXPECTED_GAPS:
        raise AssertionError(f"NODE-25 gap ledger drifted: {sorted(ids)}")


def main() -> None:
    require_python_parses()
    require_contracts()
    require_default_deny_and_hitl()
    require_side_effect_and_audit_boundary()
    require_ssrf_boundary()
    require_no_ambient_authority()
    require_gap_ledger()
    print("NODE25_TOOL_GATEWAY_STATIC_VALID")


if __name__ == "__main__":
    main()

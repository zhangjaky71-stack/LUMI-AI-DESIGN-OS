from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "services/tool-gateway/src/lumi_tool_gateway"


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-25 contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-25 marker: {needle}")


def validate_catalog() -> None:
    from lumi_tool_gateway.catalog import p0_tool_definitions
    from lumi_tool_gateway.contracts import ToolIdempotency

    definitions = p0_tool_definitions()
    names = {item.name for item in definitions}
    expected = {
        "web.search",
        "web.fetch",
        "asset.read",
        "asset.write-derived",
        "project.query",
        "artifact.query",
        "sandbox.execute",
        "media.inspect",
    }
    if names != expected:
        raise SystemExit(f"P0 tool catalog mismatch: {sorted(names)}")
    if len(definitions) != len(expected):
        raise SystemExit("P0 tool catalog contains duplicate names")
    for definition in definitions:
        if definition.is_write and definition.idempotency != ToolIdempotency.REQUIRED:
            raise SystemExit(f"write tool bypasses idempotency: {definition.key}")
    if any("sql" in item.name.lower() for item in definitions):
        raise SystemExit("unrestricted SQL tool is forbidden in NODE-25 P0")


def validate_service_import_boundary() -> None:
    forbidden_modules = {
        "asyncpg",
        "sqlalchemy",
        "boto3",
        "docker",
        "subprocess",
        "psycopg",
        "psycopg2",
    }
    for path in sorted(TOOL_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".", 1)[0] for alias in node.names}
                bad = modules & forbidden_modules
                if bad:
                    raise SystemExit(
                        f"{path}: privileged dependency bypass: {sorted(bad)}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".", 1)[0]
                if module in forbidden_modules:
                    raise SystemExit(f"{path}: privileged dependency bypass: {module}")
        for marker in (
            "/var/run/docker.sock",
            "DATABASE_URL",
            "MIGRATION_DATABASE_URL",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
        ):
            if marker in text:
                raise SystemExit(f"{path}: forbidden ambient authority marker: {marker}")


def main() -> int:
    require(
        "services/tool-gateway/src/lumi_tool_gateway/contracts.py",
        'READ_INTERNAL = "READ_INTERNAL"',
        'READ_EXTERNAL = "READ_EXTERNAL"',
        'WRITE_INTERNAL = "WRITE_INTERNAL"',
        'WRITE_EXTERNAL = "WRITE_EXTERNAL"',
        'DESTRUCTIVE = "DESTRUCTIVE"',
        'FINANCIAL = "FINANCIAL"',
        'PRIVILEGED = "PRIVILEGED"',
        "TOOL_WRITE_IDEMPOTENCY_REQUIRED",
        "ToolSideEffectContext",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/policy.py",
        "AGENT_TOOL_NOT_ALLOWED",
        "SUBAGENT_PERMISSION_ESCALATION",
        "ORG_TOOL_DENIED",
        "ToolRisk.WRITE_EXTERNAL",
        "ToolRisk.FINANCIAL",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/gateway.py",
        "permission_policy.require",
        "validate_input",
        "_approval",
        "ToolSideEffectGuardRequiredError",
        "validate_output",
        "result_offloader.store",
        "redact_arguments",
        "ToolAdapterExecutionError",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/ssrf.py",
        'scheme not in {"http", "https"}',
        "host.docker.internal",
        "metadata.google.internal",
        "not ip.is_private",
        "not ip.is_link_local",
        "pinned_ip",
    )
    require(
        "services/tool-gateway/src/lumi_tool_gateway/native.py",
        "resolved_ip=target.pinned_ip",
        "current_url = urljoin",
        "self.ssrf_policy.validate(current_url)",
        '"Authorization"',
        '"Cookie"',
        "SandboxExecutor(Protocol)",
    )
    forbid(
        "services/tool-gateway/src/lumi_tool_gateway/native.py",
        "shell=True",
        "os.system",
        "Popen(",
    )
    require(
        "services/tool-gateway/pyproject.toml",
        "dependencies = []",
    )
    validate_catalog()
    validate_service_import_boundary()
    print("NODE-25 Tool Gateway architecture/security contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = (
    "services/model-gateway/src/lumi_model_gateway/models.py",
    "services/model-gateway/src/lumi_model_gateway/gateway.py",
    "services/model-gateway/src/lumi_model_gateway/routing.py",
    "services/model-gateway/src/lumi_model_gateway/mock_provider.py",
    "services/model-gateway/src/lumi_model_gateway/openai_adapter.py",
    "services/model-gateway/src/lumi_model_gateway/anthropic_adapter.py",
    "services/model-gateway/src/lumi_model_gateway/secrets.py",
    "apps/api/src/lumi_api/model_gateway_side_effects.py",
    "apps/api/src/lumi_api/idempotency/gateway.py",
)

SDK_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+"
    r"(?:openai|anthropic|google\.genai|google\.generativeai)\b",
    re.MULTILINE,
)

OUTSIDE_GATEWAY_SCOPES = (
    ROOT / "apps/agent-runtime",
    ROOT / "apps/api",
    ROOT / "apps/worker-media",
    ROOT / "services/sandbox-runtime",
    ROOT / "services/tool-gateway",
)

SECRET_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

SECRET_READ_SCOPES = (
    ROOT / "apps/agent-runtime/src",
    ROOT / "apps/worker-media/src",
    ROOT / "services/tool-gateway/src",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def validate_required_files() -> None:
    for path in REQUIRED:
        require((ROOT / path).is_file(), f"missing required file: {path}")


def validate_provider_isolation() -> None:
    violations: list[str] = []
    for scope in OUTSIDE_GATEWAY_SCOPES:
        for path in scope.rglob("*.py"):
            if path.name == "model_gateway_side_effects.py":
                continue
            text = path.read_text(encoding="utf-8")
            if SDK_IMPORT.search(text):
                violations.append(str(path.relative_to(ROOT)))
            if "api.openai.com" in text or "api.anthropic.com" in text:
                violations.append(str(path.relative_to(ROOT)))
    require(
        not violations,
        f"provider access escaped Model Gateway: {violations}",
    )


def validate_secret_scope() -> None:
    violations: list[str] = []
    for scope in SECRET_READ_SCOPES:
        for path in scope.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(name in text for name in SECRET_NAMES):
                violations.append(str(path.relative_to(ROOT)))
    require(
        not violations,
        f"provider secret access escaped Gateway scope: {violations}",
    )


def validate_safety_markers() -> None:
    openai = read(
        "services/model-gateway/src/lumi_model_gateway/openai_adapter.py"
    )
    errors = read(
        "services/model-gateway/src/lumi_model_gateway/errors.py"
    )
    bridge = read("apps/api/src/lumi_api/model_gateway_side_effects.py")
    idempotency = read("apps/api/src/lumi_api/idempotency/gateway.py")
    http = read(
        "services/model-gateway/src/lumi_model_gateway/http_common.py"
    )
    require(
        '"store": False' in openai,
        "OpenAI Responses must explicitly set store=False",
    )
    require(
        "ProviderAcceptance.UNKNOWN" in http,
        "ambiguous transport acceptance is missing",
    )
    require(
        "SIDE_EFFECT_CONFIRMED_NOT_ACCEPTED" in bridge,
        "NODE-20 confirmed-not-accepted bridge marker missing",
    )
    require(
        "CONFIRMED_NOT_ACCEPTED_CODE" in idempotency,
        "NODE-20 safe recovery exception missing",
    )
    require("FALLBACK_ALLOWED" in errors, "fallback taxonomy missing")


def validate_packaging_boundary() -> None:
    pyproject = read("services/model-gateway/pyproject.toml")
    ledger = json.loads(
        read("reports/nodes/NODE-22/gap-ledger.json")
    )
    gap_ids = {item["id"] for item in ledger["gaps"]}
    require(
        "dependencies = []" in pyproject,
        "model-gateway unexpectedly changed frozen dependencies",
    )
    require(
        "MODEL-PACKAGE-008" in gap_ids,
        "standalone API workspace dependency gap must remain explicit",
    )


def validate_line_lengths() -> None:
    scopes = (
        ROOT / "services/model-gateway/src",
        ROOT / "services/model-gateway/tests",
        ROOT / "tools/node22",
    )
    violations: list[str] = []
    for scope in scopes:
        for path in scope.rglob("*.py"):
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                if len(line) > 100:
                    relative = path.relative_to(ROOT)
                    violations.append(
                        f"{relative}:{number}:{len(line)}"
                    )
    require(
        not violations,
        f"NODE-22 Python lines exceed 100 chars: {violations[:20]}",
    )


def main() -> None:
    checks = (
        validate_required_files,
        validate_provider_isolation,
        validate_secret_scope,
        validate_safety_markers,
        validate_packaging_boundary,
        validate_line_lengths,
    )
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print(f"NODE22_MODEL_GATEWAY_VALID: {len(checks)} checks")


if __name__ == "__main__":
    main()

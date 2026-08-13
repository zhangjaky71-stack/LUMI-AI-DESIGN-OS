from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALLER_ROOTS = (
    ROOT / "apps/api/src",
    ROOT / "apps/agent-runtime/src",
    ROOT / "apps/worker-media/src",
    ROOT / "services/sandbox-runtime/src",
    ROOT / "services/tool-gateway/src",
)
FORBIDDEN_PROVIDER_MODULES = {
    "openai",
    "anthropic",
    "cohere",
    "mistralai",
    "groq",
    "replicate",
    "fal_client",
    "together",
}
FORBIDDEN_PROVIDER_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "REPLICATE_API_TOKEN",
    "FAL_KEY",
    "TOGETHER_API_KEY",
}


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-22 contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-22 contract marker: {needle}")


def scan_callers() -> None:
    for root in CALLER_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = {alias.name.split(".", 1)[0] for alias in node.names}
                    bad = modules & FORBIDDEN_PROVIDER_MODULES
                    if bad:
                        raise SystemExit(
                            f"{path}: provider SDK import bypasses Model Gateway: {sorted(bad)}"
                        )
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module.split(".", 1)[0]
                    if module in FORBIDDEN_PROVIDER_MODULES:
                        raise SystemExit(
                            f"{path}: provider SDK import bypasses Model Gateway: {module}"
                        )
            for key in FORBIDDEN_PROVIDER_KEYS:
                if key in text:
                    raise SystemExit(
                        f"{path}: provider credential name is outside Model Gateway: {key}"
                    )


def main() -> int:
    require(
        "services/model-gateway/src/lumi_model_gateway/models.py",
        'LLM_REASONING = "llm.reasoning"',
        'IMAGE_GENERATE = "image.generate"',
        'VIDEO_TEXT_TO_VIDEO = "video.text_to_video"',
        'EMBEDDING_TEXT = "embedding.text"',
        'OCR_DOCUMENT = "ocr.document"',
        "routing_reason_codes",
        "semantic_hash",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/gateway.py",
        "PaidInvocationGuardRequiredError",
        "paid_guard is None",
        "error.delivery_state == DeliveryState.NOT_ACCEPTED",
        "AmbiguousProviderOutcomeError",
        "allow_fallback",
        "retry_after_seconds",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/routing.py",
        "CAPABILITY_MISMATCH",
        "QUALITY_BELOW_THRESHOLD",
        "PROVIDER_UNHEALTHY",
        "BUDGET_EXCEEDED",
        "PREFERRED_PROVIDER",
        "PREFERRED_MODEL",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/mock_provider.py",
        "MockFailure",
        "fixture://mock/image/",
        "fixture://mock/video/",
        "supports_streaming=True",
        "supports_async=True",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/openai_adapter.py",
        'https://api.openai.com/v1/responses',
        '"store": False',
        'Capability.LLM_STRUCTURED_OUTPUT',
        'part.get("type") == "output_text"',
        'os.getenv("OPENAI_API_KEY"',
    )
    forbid(
        "services/model-gateway/src/lumi_model_gateway/openai_adapter.py",
        "import openai",
        "from openai",
        '"store": True',
    )
    require(
        "services/model-gateway/pyproject.toml",
        "dependencies = []",
    )
    forbid(
        "services/model-gateway/src/lumi_model_gateway/telemetry.py",
        "prompt",
        "reference_assets",
        "inputs",
    )
    scan_callers()
    print("NODE-22 model gateway architecture/security contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

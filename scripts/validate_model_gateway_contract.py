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


def hosted_composition_contract() -> None:
    path = ROOT / "apps/api/src/lumi_api/model_gateway_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    factory = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "build_hosted_model_gateway"
        ),
        None,
    )
    if factory is None:
        raise SystemExit(f"{path}: hosted model gateway factory is missing")

    argument_names = {
        argument.arg
        for argument in (
            *factory.args.posonlyargs,
            *factory.args.args,
            *factory.args.kwonlyargs,
        )
    }
    forbidden_injections = argument_names & {"paid_guard", "paid_stream_guard"}
    if forbidden_injections:
        raise SystemExit(
            f"{path}: hosted composition exposes unsafe paid-guard injection: "
            f"{sorted(forbidden_injections)}"
        )

    has_postgres_guard = False
    model_gateway_paid_guard_is_bound = False
    model_gateway_stream_guard_is_injected = False
    for node in ast.walk(factory):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "paid_guard"
            for target in node.targets
        ):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "PostgresModelPaidInvocationGuard"
            ):
                has_postgres_guard = True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ModelGateway"
        ):
            for keyword in node.keywords:
                if keyword.arg == "paid_guard":
                    model_gateway_paid_guard_is_bound = (
                        isinstance(keyword.value, ast.Name)
                        and keyword.value.id == "paid_guard"
                    )
                if keyword.arg == "paid_stream_guard":
                    model_gateway_stream_guard_is_injected = True

    if not has_postgres_guard or not model_gateway_paid_guard_is_bound:
        raise SystemExit(
            f"{path}: hosted Model Gateway must bind PostgresModelPaidInvocationGuard"
        )
    if model_gateway_stream_guard_is_injected:
        raise SystemExit(
            f"{path}: hosted streaming must remain fail-closed until a durable stream guard exists"
        )


def hosted_media_contract() -> None:
    require(
        "services/model-gateway/src/lumi_model_gateway/openai_image_adapter.py",
        'https://api.openai.com/v1/images/generations',
        '_MAX_IMAGE_BYTES = 100 * 1024 * 1024',
        '_MAX_B64_CHARS',
        'base64.b64decode(b64_value, validate=True)',
        'response.headers.get("x-request-id")',
        'delivery_state=DeliveryState.ACCEPTED',
        'ProviderBinaryOutputStore',
        'ModelOutput(kind="asset_ref", value=asset_ref, mime_type=mime_type)',
        '_SUPPORTED_SIZES = frozenset({"1024x1024", "1024x1536", "1536x1024"})',
    )
    forbid(
        "services/model-gateway/src/lumi_model_gateway/openai_image_adapter.py",
        "import openai",
        "from openai",
        'ModelOutput(kind="image_base64"',
        'ModelOutput(kind="b64_json"',
    )
    require(
        "apps/api/src/lumi_api/provider_output_store.py",
        "class S3ProviderOutputStore",
        'os.getenv("LUMI_PROVIDER_OUTPUT_BUCKET", "")',
        '"provider-output/v1/"',
        "await self.object_store.put_bytes(",
        'return f"s3://{self.bucket}/{object_key}"',
        "max_image_bytes: int = _MAX_IMAGE_BYTES",
    )
    require(
        "services/asset-storage/src/lumi_asset_storage/s3.py",
        "async def put_bytes(",
        "async def get_bytes(",
        "max_bytes",
        "ChecksumSHA256",
    )
    require(
        "apps/api/src/lumi_api/model_gateway_bootstrap.py",
        "_MEDIA_PROVIDER_SECRET_SCHEMA_VERSION = 1",
        "OpenAIImageGenerationAdapter",
        "OpenAIImagePriceCard",
        "media_provider_secret",
        "provider_output_store",
        '"max_estimated_request_usd"',
        '"text_input_usd_per_million_tokens"',
        '"image_input_usd_per_million_tokens"',
        '"image_output_usd_per_million_tokens"',
    )
    require(
        "apps/api/src/lumi_api/model_gateway_service.py",
        'LUMI_MEDIA_PROVIDER_SECRET',
        "S3ProviderOutputStore.from_env()",
        "media_provider_secret=media_provider_secret",
        "provider_output_store=provider_output_store",
    )
    require(
        "services/model-gateway/tests/test_openai_image_adapter.py",
        "test_",
        "DeliveryState.ACCEPTED",
        "asset_ref",
    )
    require(
        "apps/api/tests/test_model_gateway_media_bootstrap.py",
        "build_hosted_model_gateway_from_secret",
        "provider_output_store",
    )
    require(
        "apps/api/tests/test_provider_output_store.py",
        "S3ProviderOutputStore",
        "provider-output/v1/",
    )
    require(
        "services/asset-storage/tests/test_s3_bounded_bytes.py",
        "put_bytes",
        "get_bytes",
        "max_bytes",
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
    require(
        "apps/api/src/lumi_api/model_paid_guard.py",
        "class PostgresModelPaidInvocationGuard",
        "await handle.mark_provider_attempt_started()",
        "DeliveryState.NOT_ACCEPTED",
        "RetryableSideEffectError",
        "SideEffectGateway",
        "MODEL_PAID_GUARD_RESULT_SCHEMA_UNSUPPORTED",
        "durable model result replay identity mismatch",
    )
    require(
        "apps/api/src/lumi_api/model_gateway_runtime.py",
        "PostgresModelPaidInvocationGuard",
        "LedgerBudgetGuard",
        "PostgresModelCostAccounting",
        "Streaming is intentionally fail-closed",
    )
    require(
        "apps/api/tests/integration/test_model_paid_guard_postgres.py",
        "successful_invocation_replays_without_second_provider_call",
        "not_accepted_preserves_safe_retry_semantics",
        "unknown_delivery_is_persistently_fail_closed",
        "provider_model_scope_supports_cross_provider_fallback_identity",
        "changed_semantics_on_same_paid_identity_fails_closed",
    )
    hosted_composition_contract()
    hosted_media_contract()
    scan_callers()
    print("NODE-22 model gateway architecture/security contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

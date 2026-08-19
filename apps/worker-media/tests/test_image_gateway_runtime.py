from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from lumi_image_generation.errors import ImageGenerationTransientError
from lumi_image_generation.model import (
    GatewayGenerationRequest,
    OutputRequirements,
    PromptBlocks,
)
from lumi_model_gateway.estimate_transport import HttpRouteEstimate
from lumi_model_gateway.http_transport import ModelGatewayHttpError
from lumi_model_gateway.models import (
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelResult,
    ResultStatus,
    Timing,
    Usage,
)
from lumi_worker_media.image_gateway_runtime import (
    HostedImageModelGatewayAdapter,
    S3ProviderOutputFetcher,
)


class _FakeGatewayClient:
    def __init__(self, *, output_kind: str = "asset_ref") -> None:
        self.output_kind = output_kind
        self.estimated = 0
        self.invoked = 0

    async def estimate(self, request: object) -> HttpRouteEstimate:
        del request
        self.estimated += 1
        return HttpRouteEstimate(
            provider="openai",
            model="gpt-image-1.5",
            amount_usd=Decimal("0.12"),
            confidence=CostConfidence.ESTIMATED,
            price_snapshot_id="image-price-1",
            reason_codes=("PROFILE_MATCH", "CAPABILITY_MATCH"),
        )

    async def invoke(self, request: object) -> ModelResult:
        del request
        self.invoked += 1
        return ModelResult(
            status=ResultStatus.SUCCEEDED,
            provider="openai",
            model="gpt-image-1.5",
            provider_request_id="req_image_123",
            outputs=(
                ModelOutput(
                    kind=self.output_kind,
                    value="s3://lumi-assets/provider-output/v1/org/op/abc.png",
                    mime_type="image/png",
                ),
            ),
            usage=Usage(image_output_tokens=100),
            timing=Timing(total_ms=123),
            cost=CostEstimate(
                amount_usd=Decimal("0.11"),
                confidence=CostConfidence.EXACT,
                price_snapshot_id="image-price-1",
            ),
            safety_metadata={"blocked": False},
            finish_reason="completed",
        )


class _FailingGatewayClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def estimate(self, request: object) -> HttpRouteEstimate:
        del request
        raise self.error

    async def invoke(self, request: object) -> ModelResult:
        del request
        raise AssertionError("invoke must not run when estimate failed")


class _FakeObjectStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.error = error

    async def get_bytes(self, *, bucket: str, object_key: str, max_bytes: int) -> bytes:
        self.calls.append((bucket, object_key, max_bytes))
        if self.error is not None:
            raise self.error
        return b"png-bytes"


def _request() -> GatewayGenerationRequest:
    return GatewayGenerationRequest(
        organization_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        task_id="33333333-3333-3333-3333-333333333333",
        root_operation_id="44444444-4444-4444-4444-444444444444",
        variant_operation_id="55555555-5555-5555-5555-555555555555",
        generation_id="image-generation:test",
        variant_index=1,
        mode="TEXT_TO_IMAGE",
        prompt=PromptBlocks(
            objective="Create a clean product image",
            content="A ceramic cup on a neutral background",
            visual_direction="minimal studio lighting",
            brand_constraints=(),
            identity_requirements=(),
            negative_constraints=(),
            output_dimensions="1024x1024",
            template_version="test-v1",
        ),
        references=(),
        target_width=1024,
        target_height=1024,
        quality_profile="BALANCED",
        budget_limit_usd=Decimal("1.00"),
        constraints=(),
        output_requirements=OutputRequirements(format="PNG"),
        seed=None,
        agent_run_id=None,
    )


class ImageGatewayRuntimeTests(unittest.TestCase):
    def test_private_gateway_estimate_and_invoke_map_to_node46_contract(self) -> None:
        client = _FakeGatewayClient()
        adapter = HostedImageModelGatewayAdapter(client)  # type: ignore[arg-type]
        estimate = asyncio.run(adapter.estimate(_request()))
        result = asyncio.run(adapter.invoke(_request()))
        self.assertEqual(estimate.amount_usd, Decimal("0.12"))
        self.assertEqual(estimate.provider, "openai")
        self.assertEqual(result.status, "SUCCEEDED")
        self.assertEqual(result.outputs[0].ref, "s3://lumi-assets/provider-output/v1/org/op/abc.png")
        self.assertEqual(result.routing_reason_codes, ("PROFILE_MATCH", "CAPABILITY_MATCH"))
        self.assertEqual(client.estimated, 2)
        self.assertEqual(client.invoked, 1)

    def test_non_asset_ref_result_is_rejected(self) -> None:
        adapter = HostedImageModelGatewayAdapter(
            _FakeGatewayClient(output_kind="image_base64")  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(ValueError, "IMAGE_GATEWAY_OUTPUT_MUST_BE_ASSET_REF"):
            asyncio.run(adapter.invoke(_request()))

    def test_private_gateway_503_is_retryable(self) -> None:
        adapter = HostedImageModelGatewayAdapter(
            _FailingGatewayClient(
                ModelGatewayHttpError(503, "MODEL_GATEWAY_UNAVAILABLE", "temporary")
            )  # type: ignore[arg-type]
        )
        with self.assertRaises(ImageGenerationTransientError) as raised:
            asyncio.run(adapter.estimate(_request()))
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.code, "GENERATION_GATEWAY_ESTIMATE_TEMPORARY")

    def test_private_gateway_400_remains_permanent(self) -> None:
        error = ModelGatewayHttpError(400, "MODEL_GATEWAY_BAD_REQUEST", "bad request")
        adapter = HostedImageModelGatewayAdapter(
            _FailingGatewayClient(error)  # type: ignore[arg-type]
        )
        with self.assertRaises(ModelGatewayHttpError) as raised:
            asyncio.run(adapter.estimate(_request()))
        self.assertIs(raised.exception, error)

    def test_private_gateway_transport_failure_is_retryable(self) -> None:
        adapter = HostedImageModelGatewayAdapter(
            _FailingGatewayClient(OSError("connection reset"))  # type: ignore[arg-type]
        )
        with self.assertRaises(ImageGenerationTransientError) as raised:
            asyncio.run(adapter.estimate(_request()))
        self.assertEqual(raised.exception.code, "GENERATION_GATEWAY_ESTIMATE_TEMPORARY")

    def test_fetcher_reads_only_provider_output_prefix_from_same_bucket(self) -> None:
        store = _FakeObjectStore()
        fetcher = S3ProviderOutputFetcher(
            bucket="lumi-assets",
            object_store=store,  # type: ignore[arg-type]
            max_bytes=1024,
        )
        fetched = asyncio.run(
            fetcher.fetch(
                "s3://lumi-assets/provider-output/v1/org/op/abc.png",
                "image/png",
            )
        )
        self.assertEqual(fetched.content, b"png-bytes")
        self.assertEqual(
            store.calls,
            [("lumi-assets", "provider-output/v1/org/op/abc.png", 1024)],
        )

    def test_fetcher_storage_transport_failure_is_retryable(self) -> None:
        fetcher = S3ProviderOutputFetcher(
            bucket="lumi-assets",
            object_store=_FakeObjectStore(error=RuntimeError("s3 unavailable")),  # type: ignore[arg-type]
        )
        with self.assertRaises(ImageGenerationTransientError) as raised:
            asyncio.run(
                fetcher.fetch(
                    "s3://lumi-assets/provider-output/v1/org/op/abc.png",
                    "image/png",
                )
            )
        self.assertEqual(
            raised.exception.code,
            "GENERATION_PROVIDER_OUTPUT_STORAGE_TEMPORARY",
        )

    def test_fetcher_storage_validation_failure_remains_permanent(self) -> None:
        fetcher = S3ProviderOutputFetcher(
            bucket="lumi-assets",
            object_store=_FakeObjectStore(error=ValueError("S3_OBJECT_TOO_LARGE")),  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(ValueError, "S3_OBJECT_TOO_LARGE"):
            asyncio.run(
                fetcher.fetch(
                    "s3://lumi-assets/provider-output/v1/org/op/abc.png",
                    "image/png",
                )
            )

    def test_fetcher_rejects_cross_bucket_encoded_and_traversal_refs(self) -> None:
        store = _FakeObjectStore()
        fetcher = S3ProviderOutputFetcher(
            bucket="lumi-assets",
            object_store=store,  # type: ignore[arg-type]
        )
        bad_refs = (
            "s3://other-assets/provider-output/v1/org/op/abc.png",
            "s3://lumi-assets/provider-output/v1/org/%2e%2e/abc.png",
            "s3://lumi-assets/provider-output/v1/org/../abc.png",
            "https://example.invalid/provider-output/v1/org/op/abc.png",
            "s3://lumi-assets/not-provider-output/abc.png",
        )
        for ref in bad_refs:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                asyncio.run(fetcher.fetch(ref, "image/png"))
        self.assertEqual(store.calls, [])


if __name__ == "__main__":
    unittest.main()

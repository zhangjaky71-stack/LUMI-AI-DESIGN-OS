from __future__ import annotations

import base64
import json
import unittest
from decimal import Decimal
from uuid import uuid4

from lumi_model_gateway import Capability, ModelRequest, QualityProfile, ResultStatus
from lumi_model_gateway.errors import DeliveryState, ErrorCategory, ProviderInvocationError
from lumi_model_gateway.openai_adapter import HttpResponse
from lumi_model_gateway.openai_image_adapter import (
    OpenAIImageGenerationAdapter,
    OpenAIImagePriceCard,
)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


class FakeOutputStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def store_bytes(self, **kwargs: object) -> str:
        self.calls.append(dict(kwargs))
        request = kwargs["request"]
        return f"s3://assets/provider-output/v1/{request.operation_id}/image.png"


def _price_card() -> OpenAIImagePriceCard:
    return OpenAIImagePriceCard(
        snapshot_id="image-price-test",
        max_estimated_request_usd=Decimal("0.25"),
        text_input_usd_per_million_tokens=Decimal("2"),
        image_input_usd_per_million_tokens=Decimal("4"),
        image_output_usd_per_million_tokens=Decimal("15"),
    )


def _request(
    *,
    width: int = 1024,
    height: int = 1024,
    output_format: str = "png",
    transparent: bool = False,
    capability: Capability = Capability.IMAGE_GENERATE,
) -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        generation_id=uuid4(),
        capability=capability,
        quality_profile=QualityProfile.HIGH,
        inputs={
            "prompt_blocks": {
                "objective": "Create a premium product hero image",
                "content": "A matte black coffee cup on stone",
                "visual_direction": "minimal studio light",
                "brand_constraints": ["no logos"],
                "identity_requirements": [],
                "negative_constraints": ["no text"],
                "output_dimensions": f"{width}x{height}",
            },
            "width": width,
            "height": height,
            "format": output_format,
            "transparent_background": transparent,
            "seed": None,
        },
        constraints={
            "target_width": width,
            "target_height": height,
            "output_format": output_format,
            "transparent_background": transparent,
        },
        budget_limit_usd=Decimal("1.00"),
    )


def _body(raw: bytes = b"fake-png") -> bytes:
    return json.dumps(
        {
            "created": 1,
            "data": [{"b64_json": base64.b64encode(raw).decode("ascii")}],
            "usage": {
                "input_tokens": 50,
                "output_tokens": 50,
                "total_tokens": 100,
                "input_tokens_details": {"text_tokens": 10, "image_tokens": 40},
            },
        }
    ).encode()


class OpenAIImageAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_bytes_are_staged_and_only_asset_ref_crosses_gateway(self) -> None:
        transport = FakeTransport(
            [HttpResponse(200, {"x-request-id": "req_image_1"}, _body())]
        )
        output_store = FakeOutputStore()
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=output_store,
            transport=transport,
        )
        request = _request()
        estimate = await adapter.estimate_cost(request)
        self.assertEqual(estimate.amount_usd, Decimal("0.25"))

        result = await adapter.invoke(request)
        self.assertEqual(result.status, ResultStatus.SUCCEEDED)
        self.assertEqual(result.provider_request_id, "req_image_1")
        self.assertEqual(result.outputs[0].kind, "asset_ref")
        self.assertTrue(str(result.outputs[0].value).startswith("s3://assets/"))
        self.assertNotIn(base64.b64encode(b"fake-png").decode("ascii"), repr(result))
        self.assertEqual(result.usage.image_input_tokens, 40)
        self.assertEqual(result.usage.image_output_tokens, 50)
        self.assertEqual(result.cost.amount_usd, Decimal("0.000930"))
        self.assertEqual(result.cost.price_snapshot_id, "image-price-test")

        stored = output_store.calls[0]
        self.assertEqual(stored["data"], b"fake-png")
        self.assertEqual(stored["content_type"], "image/png")
        self.assertEqual(stored["extension"], "png")

        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://api.openai.com/v1/images/generations")
        payload = json.loads(call["body"])
        self.assertEqual(payload["model"], "gpt-image-test")
        self.assertEqual(payload["size"], "1024x1024")
        self.assertEqual(payload["quality"], "high")
        self.assertEqual(payload["output_format"], "png")
        self.assertEqual(payload["n"], 1)
        self.assertIn("Objective:", payload["prompt"])
        self.assertIn("Negative constraints: no text", payload["prompt"])

    async def test_transparent_generation_uses_transparent_background(self) -> None:
        transport = FakeTransport(
            [HttpResponse(200, {"x-request-id": "req_transparent"}, _body())]
        )
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=transport,
        )
        await adapter.invoke(
            _request(
                transparent=True,
                capability=Capability.IMAGE_TRANSPARENT_BACKGROUND,
            )
        )
        payload = json.loads(transport.calls[0]["body"])
        self.assertEqual(payload["background"], "transparent")

    async def test_arbitrary_exact_size_fails_before_transport(self) -> None:
        transport = FakeTransport([])
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=transport,
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(_request(width=750, height=1624))
        self.assertEqual(raised.exception.delivery_state, DeliveryState.NOT_ACCEPTED)
        self.assertEqual(raised.exception.category, ErrorCategory.HARD_CONSTRAINT_INVALID)
        self.assertEqual(transport.calls, [])

    async def test_deterministic_seed_is_rejected_instead_of_silently_ignored(self) -> None:
        request = _request()
        request.inputs["seed"] = 42
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=FakeTransport([]),
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(request)
        self.assertEqual(raised.exception.delivery_state, DeliveryState.NOT_ACCEPTED)

    async def test_success_without_server_request_id_is_accepted_and_unsafe_to_retry(self) -> None:
        output_store = FakeOutputStore()
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=output_store,
            transport=FakeTransport([HttpResponse(200, {}, _body())]),
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(_request())
        self.assertEqual(raised.exception.delivery_state, DeliveryState.ACCEPTED)
        self.assertTrue(raised.exception.ambiguous)
        self.assertEqual(output_store.calls, [])

    async def test_429_is_not_accepted_but_5xx_is_ambiguous(self) -> None:
        rate_limited = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=FakeTransport(
                [HttpResponse(429, {}, b'{"error":{"message":"rate","code":"rate_limit"}}')]
            ),
        )
        with self.assertRaises(ProviderInvocationError) as raised_429:
            await rate_limited.invoke(_request())
        self.assertEqual(raised_429.exception.delivery_state, DeliveryState.NOT_ACCEPTED)
        self.assertEqual(raised_429.exception.category, ErrorCategory.RATE_LIMIT)

        failed = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=FakeTransport(
                [HttpResponse(503, {}, b'{"error":{"message":"failed","code":"server"}}')]
            ),
        )
        with self.assertRaises(ProviderInvocationError) as raised_503:
            await failed.invoke(_request())
        self.assertEqual(raised_503.exception.delivery_state, DeliveryState.UNKNOWN)
        self.assertFalse(raised_503.exception.fallbackable)

    async def test_invalid_base64_after_200_is_accepted_and_ambiguous(self) -> None:
        body = json.dumps(
            {
                "data": [{"b64_json": "%%%not-base64%%%"}],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "input_tokens_details": {"text_tokens": 1, "image_tokens": 0},
                },
            }
        ).encode()
        adapter = OpenAIImageGenerationAdapter(
            api_key="test-key-not-real",
            model="gpt-image-test",
            price_card=_price_card(),
            output_store=FakeOutputStore(),
            transport=FakeTransport([HttpResponse(200, {"x-request-id": "req_bad"}, body)]),
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(_request())
        self.assertEqual(raised.exception.delivery_state, DeliveryState.ACCEPTED)


if __name__ == "__main__":
    unittest.main()

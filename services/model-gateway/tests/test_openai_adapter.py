from __future__ import annotations

import json
import unittest
from decimal import Decimal
from uuid import uuid4

from lumi_model_gateway import Capability, ModelRequest, ResultStatus
from lumi_model_gateway.errors import DeliveryState, ErrorCategory, ProviderInvocationError
from lumi_model_gateway.openai_adapter import (
    HttpResponse,
    OpenAIResponsesAdapter,
)
from lumi_model_gateway.pricing import PriceCard


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


def price_card() -> PriceCard:
    return PriceCard(
        snapshot_id="openai-test-prices",
        input_usd_per_million_tokens=Decimal("2"),
        output_usd_per_million_tokens=Decimal("8"),
    )


def text_request() -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "Hello"},
    )


def completed_body(text: str = "Hello from Responses") -> bytes:
    return json.dumps(
        {
            "id": "resp_test_123",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "input_tokens_details": {"cached_tokens": 2},
            },
        }
    ).encode()


class OpenAIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_responses_request_is_minimal_and_store_false(self) -> None:
        transport = FakeTransport([HttpResponse(200, {}, completed_body())])
        adapter = OpenAIResponsesAdapter(
            api_key="test-key-not-a-real-secret",
            model="gpt-5",
            price_card=price_card(),
            transport=transport,
        )
        result = await adapter.invoke(text_request())
        self.assertEqual(result.status, ResultStatus.SUCCEEDED)
        self.assertEqual(result.outputs[0].value, "Hello from Responses")
        self.assertEqual(result.provider_request_id, "resp_test_123")
        self.assertEqual(result.usage.cached_input_tokens, 2)
        self.assertEqual(result.cost.amount_usd, Decimal("0.000060"))
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://api.openai.com/v1/responses")
        payload = json.loads(call["body"])
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["model"], "gpt-5")
        self.assertEqual(payload["input"], "Hello")
        headers = call["headers"]
        self.assertEqual(headers["authorization"], "Bearer test-key-not-a-real-secret")
        self.assertNotIn("test-key-not-a-real-secret", repr(adapter))

    async def test_structured_output_uses_text_format_json_schema(self) -> None:
        transport = FakeTransport(
            [HttpResponse(200, {}, completed_body('{"answer":"ok"}'))]
        )
        adapter = OpenAIResponsesAdapter(
            api_key="test-key-not-a-real-secret",
            model="gpt-5",
            price_card=price_card(),
            transport=transport,
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_STRUCTURED_OUTPUT,
            inputs={"prompt": "Return JSON"},
            structured_output_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )
        result = await adapter.invoke(request)
        self.assertEqual(result.outputs[0].kind, "json")
        self.assertEqual(result.outputs[0].value, {"answer": "ok"})
        payload = json.loads(transport.calls[0]["body"])
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])

    async def test_429_is_safe_not_accepted_with_retry_after(self) -> None:
        body = json.dumps(
            {"error": {"message": "rate limited", "code": "rate_limit"}}
        ).encode()
        transport = FakeTransport(
            [HttpResponse(429, {"retry-after": "2.5"}, body)]
        )
        adapter = OpenAIResponsesAdapter(
            api_key="test-key-not-a-real-secret",
            model="gpt-5",
            price_card=price_card(),
            transport=transport,
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(text_request())
        error = raised.exception
        self.assertEqual(error.category, ErrorCategory.RATE_LIMIT)
        self.assertEqual(error.delivery_state, DeliveryState.NOT_ACCEPTED)
        self.assertTrue(error.fallbackable)
        self.assertEqual(error.retry_after_seconds, 2.5)

    async def test_5xx_is_ambiguous_and_not_cross_fallbackable(self) -> None:
        body = json.dumps(
            {"error": {"message": "provider failed", "code": "server_error"}}
        ).encode()
        transport = FakeTransport([HttpResponse(503, {}, body)])
        adapter = OpenAIResponsesAdapter(
            api_key="test-key-not-a-real-secret",
            model="gpt-5",
            price_card=price_card(),
            transport=transport,
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(text_request())
        error = raised.exception
        self.assertEqual(error.category, ErrorCategory.PROVIDER_5XX)
        self.assertEqual(error.delivery_state, DeliveryState.UNKNOWN)
        self.assertTrue(error.ambiguous)
        self.assertFalse(error.fallbackable)

    async def test_provider_native_fields_are_rejected_at_boundary(self) -> None:
        adapter = OpenAIResponsesAdapter(
            api_key="test-key-not-a-real-secret",
            model="gpt-5",
            price_card=price_card(),
            transport=FakeTransport([]),
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                        "provider_parameter": "forbidden",
                    }
                ]
            },
        )
        with self.assertRaises(ProviderInvocationError):
            adapter.validate(request)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from uuid import uuid4

from lumi_model_gateway import Capability, ModelRequest
from lumi_model_gateway.errors import DeliveryState, ProviderInvocationError
from lumi_model_gateway.openai_adapter import HttpResponse
from lumi_model_gateway.openai_tool_adapter import OpenAIResponsesToolAdapter
from lumi_model_gateway.pricing import PriceCard


class FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
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
                "headers": headers,
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def _price_card() -> PriceCard:
    return PriceCard(
        snapshot_id="tool-test",
        input_usd_per_million_tokens=Decimal("1"),
        output_usd_per_million_tokens=Decimal("1"),
    )


def _tool_request(messages: list[dict[str, object]]) -> ModelRequest:
    return ModelRequest(
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={
            "messages": messages,
            "tools": [
                {
                    "name": "lookup_asset",
                    "description": "Look up an asset by id",
                    "parameters": {
                        "type": "object",
                        "properties": {"asset_id": {"type": "string"}},
                        "required": ["asset_id"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        },
    )


class OpenAIResponsesToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_emits_provider_function_definition_and_parses_tool_call(self) -> None:
        body = json.dumps(
            {
                "id": "resp_tool_1",
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_123",
                        "name": "lookup_asset",
                        "arguments": '{"asset_id":"asset-42"}',
                        "status": "completed",
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
            }
        ).encode()
        transport = FakeTransport(HttpResponse(200, {}, body))
        adapter = OpenAIResponsesToolAdapter(
            api_key="test-key-not-real",
            model="gpt-5",
            price_card=_price_card(),
            transport=transport,
        )
        request = _tool_request([{"role": "user", "content": "Find asset 42"}])
        result = await adapter.invoke(request)
        self.assertEqual(len(result.outputs), 1)
        self.assertEqual(result.outputs[0].kind, "tool_call")
        self.assertEqual(
            result.outputs[0].value,
            {"id": "call_123", "name": "lookup_asset", "args": {"asset_id": "asset-42"}},
        )
        payload = json.loads(transport.calls[0]["body"])
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(payload["tools"][0]["name"], "lookup_asset")
        self.assertTrue(payload["tools"][0]["strict"])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertIs(payload["parallel_tool_calls"], False)
        self.assertIs(payload["store"], False)

    async def test_maps_assistant_tool_call_and_tool_result_back_into_responses_input(self) -> None:
        body = json.dumps(
            {
                "id": "resp_tool_2",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Asset found"}],
                    }
                ],
                "usage": {"input_tokens": 30, "output_tokens": 3, "total_tokens": 33},
            }
        ).encode()
        transport = FakeTransport(HttpResponse(200, {}, body))
        adapter = OpenAIResponsesToolAdapter(
            api_key="test-key-not-real",
            model="gpt-5",
            price_card=_price_card(),
            transport=transport,
        )
        request = _tool_request(
            [
                {"role": "user", "content": "Find asset 42"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "name": "lookup_asset",
                            "args": {"asset_id": "asset-42"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_123",
                    "content": '{"name":"Poster"}',
                },
            ]
        )
        result = await adapter.invoke(request)
        self.assertEqual(result.outputs[0].kind, "text")
        self.assertEqual(result.outputs[0].value, "Asset found")
        payload = json.loads(transport.calls[0]["body"])
        self.assertEqual(
            payload["input"][1],
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "lookup_asset",
                "arguments": '{"asset_id":"asset-42"}',
            },
        )
        self.assertEqual(
            payload["input"][2],
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": '{"name":"Poster"}',
            },
        )

    async def test_provider_native_tool_fields_are_rejected(self) -> None:
        adapter = OpenAIResponsesToolAdapter(
            api_key="test-key-not-real",
            model="gpt-5",
            price_card=_price_card(),
            transport=FakeTransport(HttpResponse(200, {}, b"{}")),
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={
                "prompt": "hello",
                "tools": [
                    {
                        "type": "function",
                        "name": "forbidden-native-shape",
                        "parameters": {"type": "object"},
                    }
                ],
            },
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            adapter.validate(request)
        self.assertEqual(raised.exception.delivery_state, DeliveryState.NOT_ACCEPTED)

    async def test_invalid_provider_tool_arguments_are_accepted_ambiguous(self) -> None:
        body = json.dumps(
            {
                "id": "resp_bad_tool",
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_bad",
                        "name": "lookup_asset",
                        "arguments": "not-json",
                    }
                ],
            }
        ).encode()
        adapter = OpenAIResponsesToolAdapter(
            api_key="test-key-not-real",
            model="gpt-5",
            price_card=_price_card(),
            transport=FakeTransport(HttpResponse(200, {}, body)),
        )
        with self.assertRaises(ProviderInvocationError) as raised:
            await adapter.invoke(_tool_request([{"role": "user", "content": "go"}]))
        self.assertEqual(raised.exception.delivery_state, DeliveryState.ACCEPTED)
        self.assertTrue(raised.exception.ambiguous)


if __name__ == "__main__":
    unittest.main()

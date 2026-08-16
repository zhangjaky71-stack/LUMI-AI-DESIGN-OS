from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

import lumi_model_gateway.anthropic_adapter as anthropic_module
import lumi_model_gateway.openai_adapter as openai_module
from lumi_model_gateway.anthropic_adapter import AnthropicMessagesAdapter
from lumi_model_gateway.http_common import JsonHttpResponse
from lumi_model_gateway.models import Capability, ModelInput, ModelRequest
from lumi_model_gateway.openai_adapter import OpenAIResponsesAdapter
from lumi_model_gateway.secrets import MappingSecretProvider

ORG = UUID("01910000-0000-7000-8000-000000000421")
OP = UUID("01910000-0000-7000-8000-000000000422")
REQ = UUID("01910000-0000-7000-8000-000000000423")


def structured_request() -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.LLM_STRUCTURED_OUTPUT,
        inputs=(ModelInput(kind="text", text="return one title"),),
        budget_limit=Decimal("1"),
        structured_output_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
        constraints={"max_output_tokens": 50},
    )


def reasoning_request() -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind="text", text="hello"),),
        budget_limit=Decimal("1"),
        constraints={"max_output_tokens": 50},
    )


def test_openai_responses_payload_and_normalization_do_not_leak_secret() -> None:
    secret = "sk-node22-openai-canary"
    adapter = OpenAIResponsesAdapter(
        MappingSecretProvider({("openai", "api_key"): secret}),
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
    )
    captured = {}
    original = openai_module.json_request

    async def fake_request(**kwargs):
        captured.update(kwargs)
        return JsonHttpResponse(
            200,
            {},
            {
                "id": "resp_123",
                "status": "completed",
                "output_text": '{"title":"LUMI"}',
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 2},
                },
            },
        )

    openai_module.json_request = fake_request
    try:
        result = asyncio.run(adapter.invoke(structured_request(), adapter.models()[0]))
    finally:
        openai_module.json_request = original

    assert captured["url"].endswith("/v1/responses")
    assert captured["payload"]["store"] is False
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"
    assert captured["headers"]["X-Client-Request-Id"] == str(REQ)
    assert captured["headers"]["Authorization"] == f"Bearer {secret}"
    assert result.outputs[0].json_value == {"title": "LUMI"}
    assert result.usage.cached_input_tokens == 2
    assert secret not in repr(result)


def test_anthropic_messages_headers_and_normalization_do_not_leak_secret() -> None:
    secret = "sk-ant-node22-canary"
    adapter = AnthropicMessagesAdapter(
        MappingSecretProvider({("anthropic", "api_key"): secret}),
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
    )
    captured = {}
    original = anthropic_module.json_request

    async def fake_request(**kwargs):
        captured.update(kwargs)
        return JsonHttpResponse(
            200,
            {},
            {
                "id": "msg_123",
                "content": [{"type": "text", "text": "anthropic-ok"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 7,
                    "cache_read_input_tokens": 3,
                },
            },
        )

    anthropic_module.json_request = fake_request
    try:
        result = asyncio.run(adapter.invoke(reasoning_request(), adapter.models()[0]))
    finally:
        anthropic_module.json_request = original

    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == secret
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["max_tokens"] == 50
    assert result.outputs[0].text == "anthropic-ok"
    assert result.usage.cached_input_tokens == 3
    assert secret not in repr(result)

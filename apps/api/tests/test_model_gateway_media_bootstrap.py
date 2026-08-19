from __future__ import annotations

import json
import unittest

from lumi_model_gateway.openai_image_adapter import OpenAIImageGenerationAdapter
from lumi_model_gateway.openai_tool_adapter import OpenAIResponsesToolAdapter

from lumi_api.model_gateway_bootstrap import (
    ModelGatewayBootstrapError,
    build_hosted_model_gateway_from_secret,
)


class FakeOutputStore:
    async def store_bytes(self, **kwargs: object) -> str:
        del kwargs
        return "s3://assets/provider-output/v1/test.png"


def _model_secret() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "provider": "openai",
            "api_key": "test-text-key-not-real",
            "models": [
                {
                    "name": "text-model-test",
                    "profiles": ["reasoning.high"],
                    "price": {
                        "snapshot_id": "text-price-test",
                        "input_usd_per_million_tokens": "2",
                        "output_usd_per_million_tokens": "8",
                    },
                }
            ],
        }
    )


def _media_secret(*, model: str = "image-model-test") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "provider": "openai",
            "api_key": "test-media-key-not-real",
            "timeout_seconds": 180,
            "image_models": [
                {
                    "name": model,
                    "profiles": ["image.high"],
                    "quality_score": 95,
                    "price": {
                        "snapshot_id": "image-price-test",
                        "max_estimated_request_usd": "0.50",
                        "text_input_usd_per_million_tokens": "2",
                        "image_input_usd_per_million_tokens": "4",
                        "image_output_usd_per_million_tokens": "15",
                    },
                }
            ],
        }
    )


class HostedMediaBootstrapTests(unittest.TestCase):
    def test_text_and_image_models_share_one_hosted_registry(self) -> None:
        bootstrap = build_hosted_model_gateway_from_secret(
            database_dsn="postgresql://user:pass@localhost/lumi",
            provider_secret=_model_secret(),
            media_provider_secret=_media_secret(),
            provider_output_store=FakeOutputStore(),
        )
        adapters = bootstrap.api.gateway.registry.adapters()
        self.assertEqual(bootstrap.provider_count, 1)
        self.assertEqual(bootstrap.model_count, 2)
        self.assertEqual(bootstrap.profile_count, 2)
        self.assertTrue(any(isinstance(item, OpenAIResponsesToolAdapter) for item in adapters))
        self.assertTrue(any(isinstance(item, OpenAIImageGenerationAdapter) for item in adapters))

    def test_media_secret_without_output_store_fails_closed(self) -> None:
        with self.assertRaises(ModelGatewayBootstrapError):
            build_hosted_model_gateway_from_secret(
                database_dsn="postgresql://user:pass@localhost/lumi",
                provider_secret=_model_secret(),
                media_provider_secret=_media_secret(),
            )

    def test_media_price_ceiling_must_be_positive_decimal_string(self) -> None:
        payload = json.loads(_media_secret())
        payload["image_models"][0]["price"]["max_estimated_request_usd"] = "0"
        with self.assertRaises(ModelGatewayBootstrapError):
            build_hosted_model_gateway_from_secret(
                database_dsn="postgresql://user:pass@localhost/lumi",
                provider_secret=_model_secret(),
                media_provider_secret=json.dumps(payload),
                provider_output_store=FakeOutputStore(),
            )

    def test_text_and_media_cannot_register_same_provider_model_key(self) -> None:
        with self.assertRaises(ModelGatewayBootstrapError):
            build_hosted_model_gateway_from_secret(
                database_dsn="postgresql://user:pass@localhost/lumi",
                provider_secret=_model_secret(),
                media_provider_secret=_media_secret(model="text-model-test"),
                provider_output_store=FakeOutputStore(),
            )

    def test_unknown_media_secret_fields_are_rejected(self) -> None:
        payload = json.loads(_media_secret())
        payload["provider_native_escape_hatch"] = True
        with self.assertRaises(ModelGatewayBootstrapError):
            build_hosted_model_gateway_from_secret(
                database_dsn="postgresql://user:pass@localhost/lumi",
                provider_secret=_model_secret(),
                media_provider_secret=json.dumps(payload),
                provider_output_store=FakeOutputStore(),
            )


if __name__ == "__main__":
    unittest.main()

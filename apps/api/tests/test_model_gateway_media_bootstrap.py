from __future__ import annotations

import json
import unittest

from lumi_model_gateway.openai_image_adapter import OpenAIImageGenerationAdapter
from lumi_model_gateway.openai_tool_adapter import OpenAIResponsesToolAdapter
from lumi_model_gateway.openai_video_adapter import OpenAIVideoGenerationAdapter

from lumi_api.model_gateway_bootstrap import (
    ModelGatewayBootstrapError,
    build_hosted_model_gateway_from_secret,
)


class FakeOutputStore:
    async def store_bytes(self, **kwargs: object) -> str:
        del kwargs
        return "s3://assets/provider-output/v1/test.png"

    async def store_path(self, **kwargs: object) -> str:
        del kwargs
        return "s3://assets/provider-output/v1/test.mp4"

    async def store_async_path(self, **kwargs: object) -> str:
        del kwargs
        return "s3://assets/provider-output/v1/async/test.mp4"


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


def _media_secret_v2() -> str:
    return json.dumps(
        {
            "schema_version": 2,
            "provider": "openai",
            "api_key": "test-media-key-not-real",
            "timeout_seconds": 180,
            "image_models": [
                {
                    "name": "image-model-test",
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
            "video_models": [
                {
                    "name": "sora-2",
                    "profiles": ["video.high"],
                    "quality_score": 94,
                    "price": {
                        "snapshot_id": "video-price-test",
                        "usd_per_second_by_size": {
                            "1280x720": "0.10",
                            "720x1280": "0.10",
                        },
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
        self.assertFalse(any(isinstance(item, OpenAIVideoGenerationAdapter) for item in adapters))

    def test_v2_registers_video_model_in_same_private_gateway_registry(self) -> None:
        bootstrap = build_hosted_model_gateway_from_secret(
            database_dsn="postgresql://user:pass@localhost/lumi",
            provider_secret=_model_secret(),
            media_provider_secret=_media_secret_v2(),
            provider_output_store=FakeOutputStore(),
        )
        adapters = bootstrap.api.gateway.registry.adapters()
        video = [item for item in adapters if isinstance(item, OpenAIVideoGenerationAdapter)]
        self.assertEqual(bootstrap.provider_count, 1)
        self.assertEqual(bootstrap.model_count, 3)
        self.assertEqual(bootstrap.profile_count, 3)
        self.assertEqual(len(video), 1)
        self.assertEqual(video[0].descriptor.model, "sora-2")
        self.assertTrue(video[0].descriptor.supports_async)

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

    def test_video_prices_must_be_positive_decimal_strings(self) -> None:
        payload = json.loads(_media_secret_v2())
        payload["video_models"][0]["price"]["usd_per_second_by_size"]["1280x720"] = 0.10
        with self.assertRaises(ModelGatewayBootstrapError):
            build_hosted_model_gateway_from_secret(
                database_dsn="postgresql://user:pass@localhost/lumi",
                provider_secret=_model_secret(),
                media_provider_secret=json.dumps(payload),
                provider_output_store=FakeOutputStore(),
            )

    def test_v1_rejects_video_models_instead_of_silently_ignoring_them(self) -> None:
        payload = json.loads(_media_secret())
        payload["video_models"] = json.loads(_media_secret_v2())["video_models"]
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

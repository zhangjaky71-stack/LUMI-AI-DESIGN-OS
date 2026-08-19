from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from lumi_model_gateway import (
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    ModelGatewayAPI,
    ModelRouter,
    OpenAIResponsesAdapter,
    PriceCard,
)

from .model_gateway_runtime import build_hosted_model_gateway

_PROVIDER_SECRET_SCHEMA_VERSION = 1
_MAX_MODELS = 32


class ModelGatewayBootstrapError(RuntimeError):
    code = "MODEL_GATEWAY_BOOTSTRAP_INVALID"


@dataclass(frozen=True, slots=True)
class HostedModelGatewayBootstrap:
    api: ModelGatewayAPI
    provider_count: int
    model_count: int


def build_hosted_model_gateway_from_secret(
    *,
    database_dsn: str,
    provider_secret: str,
) -> HostedModelGatewayBootstrap:
    config = _parse_provider_secret(provider_secret)
    registry = InMemoryProviderRegistry()
    if config["provider"] != "openai":
        raise ModelGatewayBootstrapError("unsupported model provider kind")

    api_key = _required_string(config, "api_key", max_length=8192)
    organization = _optional_string(config.get("organization"), max_length=512)
    project = _optional_string(config.get("project"), max_length=512)
    timeout_seconds = _timeout_seconds(config.get("timeout_seconds", 60))
    models = config["models"]
    assert isinstance(models, list)
    for raw_model in models:
        if not isinstance(raw_model, dict):
            raise ModelGatewayBootstrapError("provider model config must be an object")
        _reject_unknown_keys(raw_model, {"name", "price"}, scope="model")
        model = _required_string(raw_model, "name", max_length=255)
        raw_price = raw_model.get("price")
        if not isinstance(raw_price, dict):
            raise ModelGatewayBootstrapError(f"price config is required for model {model}")
        _reject_unknown_keys(
            raw_price,
            {
                "snapshot_id",
                "input_usd_per_million_tokens",
                "output_usd_per_million_tokens",
            },
            scope=f"price:{model}",
        )
        price_card = PriceCard(
            snapshot_id=_required_string(raw_price, "snapshot_id", max_length=128),
            input_usd_per_million_tokens=_required_money_decimal(
                raw_price,
                "input_usd_per_million_tokens",
            ),
            output_usd_per_million_tokens=_required_money_decimal(
                raw_price,
                "output_usd_per_million_tokens",
            ),
        )
        registry.register(
            OpenAIResponsesAdapter(
                api_key=api_key,
                model=model,
                price_card=price_card,
                organization=organization,
                project=project,
                timeout_seconds=timeout_seconds,
            )
        )

    health = InMemoryProviderHealthRegistry()
    router = ModelRouter(registry=registry, health=health)
    return HostedModelGatewayBootstrap(
        api=build_hosted_model_gateway(
            database_dsn=database_dsn,
            registry=registry,
            health=health,
            router=router,
        ),
        provider_count=1,
        model_count=len(models),
    )


def _parse_provider_secret(raw: str) -> dict[str, Any]:
    if not raw or len(raw) > 262_144:
        raise ModelGatewayBootstrapError("model provider secret is missing or too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelGatewayBootstrapError("model provider secret must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelGatewayBootstrapError("model provider secret must be a JSON object")
    _reject_unknown_keys(
        payload,
        {
            "schema_version",
            "provider",
            "api_key",
            "organization",
            "project",
            "timeout_seconds",
            "models",
        },
        scope="root",
    )
    if payload.get("schema_version") != _PROVIDER_SECRET_SCHEMA_VERSION:
        raise ModelGatewayBootstrapError("unsupported model provider secret schema version")
    provider = _required_string(payload, "provider", max_length=100)
    if provider != "openai":
        raise ModelGatewayBootstrapError("only the openai hosted adapter is currently enabled")
    _required_string(payload, "api_key", max_length=8192)
    models = payload.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= _MAX_MODELS:
        raise ModelGatewayBootstrapError("model provider secret requires 1..32 models")
    names: set[str] = set()
    for raw_model in models:
        if not isinstance(raw_model, dict):
            raise ModelGatewayBootstrapError("provider model config must be an object")
        name = _required_string(raw_model, "name", max_length=255)
        if name in names:
            raise ModelGatewayBootstrapError(f"duplicate provider model: {name}")
        names.add(name)
    return payload


def _required_money_decimal(payload: dict[str, Any], key: str) -> Decimal:
    raw = payload.get(key)
    if not isinstance(raw, str) or not raw:
        raise ModelGatewayBootstrapError(f"{key} must be a decimal string")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ModelGatewayBootstrapError(f"{key} must be a decimal string") from exc
    if not value.is_finite() or value < 0:
        raise ModelGatewayBootstrapError(f"{key} must be finite and non-negative")
    return value


def _required_string(payload: dict[str, Any], key: str, *, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ModelGatewayBootstrapError(f"invalid {key}")
    return value


def _optional_string(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ModelGatewayBootstrapError("invalid optional provider string")
    return value


def _timeout_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelGatewayBootstrapError("provider timeout_seconds must be numeric")
    timeout = float(value)
    if not 1 <= timeout <= 300:
        raise ModelGatewayBootstrapError("provider timeout_seconds must be within 1..300")
    return timeout


def _reject_unknown_keys(payload: dict[str, Any], allowed: set[str], *, scope: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ModelGatewayBootstrapError(
            f"unknown {scope} provider config fields: {','.join(sorted(unknown))}"
        )

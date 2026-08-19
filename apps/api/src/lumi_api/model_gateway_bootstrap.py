from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from lumi_model_gateway import (
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    ModelGatewayAPI,
    PriceCard,
)
from lumi_model_gateway.media_output import ProviderBinaryOutputStore
from lumi_model_gateway.openai_image_adapter import (
    OpenAIImageGenerationAdapter,
    OpenAIImagePriceCard,
)
from lumi_model_gateway.openai_tool_adapter import OpenAIResponsesToolAdapter
from lumi_model_gateway.profile_routing import ModelProfileRouter

from .model_gateway_runtime import build_hosted_model_gateway

_PROVIDER_SECRET_SCHEMA_VERSION = 1
_MEDIA_PROVIDER_SECRET_SCHEMA_VERSION = 1
_MAX_MODELS = 32
_MAX_PROFILES_PER_MODEL = 16
_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")


class ModelGatewayBootstrapError(RuntimeError):
    code = "MODEL_GATEWAY_BOOTSTRAP_INVALID"


@dataclass(frozen=True, slots=True)
class HostedModelGatewayBootstrap:
    api: ModelGatewayAPI
    provider_count: int
    model_count: int
    profile_count: int


def build_hosted_model_gateway_from_secret(
    *,
    database_dsn: str,
    provider_secret: str,
    media_provider_secret: str | None = None,
    provider_output_store: ProviderBinaryOutputStore | None = None,
) -> HostedModelGatewayBootstrap:
    config = _parse_provider_secret(provider_secret)
    media_config = (
        _parse_media_provider_secret(media_provider_secret)
        if media_provider_secret is not None
        else None
    )
    if media_config is not None and provider_output_store is None:
        raise ModelGatewayBootstrapError(
            "media provider secret requires a provider output store"
        )

    registry = InMemoryProviderRegistry()
    profile_routes: dict[str, set[str]] = {}
    registered_keys: set[str] = set()

    _register_text_models(
        config=config,
        registry=registry,
        profile_routes=profile_routes,
        registered_keys=registered_keys,
    )
    media_model_count = 0
    if media_config is not None:
        assert provider_output_store is not None
        media_model_count = _register_image_models(
            config=media_config,
            output_store=provider_output_store,
            registry=registry,
            profile_routes=profile_routes,
            registered_keys=registered_keys,
        )

    health = InMemoryProviderHealthRegistry()
    router = ModelProfileRouter(
        registry=registry,
        health=health,
        profile_routes={
            profile: frozenset(keys) for profile, keys in profile_routes.items()
        },
    )
    text_models = config["models"]
    assert isinstance(text_models, list)
    return HostedModelGatewayBootstrap(
        api=build_hosted_model_gateway(
            database_dsn=database_dsn,
            registry=registry,
            health=health,
            router=router,
        ),
        provider_count=1,
        model_count=len(text_models) + media_model_count,
        profile_count=len(profile_routes),
    )


def _register_text_models(
    *,
    config: dict[str, Any],
    registry: InMemoryProviderRegistry,
    profile_routes: dict[str, set[str]],
    registered_keys: set[str],
) -> None:
    if config["provider"] != "openai":
        raise ModelGatewayBootstrapError("unsupported model provider kind")
    api_key = _required_string(config, "api_key", max_length=8192)
    organization = _optional_string(config.get("organization"), max_length=512)
    project = _optional_string(config.get("project"), max_length=512)
    timeout_seconds = _timeout_seconds(config.get("timeout_seconds", 60), maximum=300)
    models = config["models"]
    assert isinstance(models, list)
    for raw_model in models:
        if not isinstance(raw_model, dict):
            raise ModelGatewayBootstrapError("provider model config must be an object")
        _reject_unknown_keys(raw_model, {"name", "profiles", "price"}, scope="model")
        model = _required_string(raw_model, "name", max_length=255)
        profiles = _required_profiles(raw_model)
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
        adapter = OpenAIResponsesToolAdapter(
            api_key=api_key,
            model=model,
            price_card=PriceCard(
                snapshot_id=_required_string(raw_price, "snapshot_id", max_length=128),
                input_usd_per_million_tokens=_required_money_decimal(
                    raw_price,
                    "input_usd_per_million_tokens",
                ),
                output_usd_per_million_tokens=_required_money_decimal(
                    raw_price,
                    "output_usd_per_million_tokens",
                ),
            ),
            organization=organization,
            project=project,
            timeout_seconds=timeout_seconds,
        )
        _register_adapter(
            adapter=adapter,
            profiles=profiles,
            registry=registry,
            profile_routes=profile_routes,
            registered_keys=registered_keys,
        )


def _register_image_models(
    *,
    config: dict[str, Any],
    output_store: ProviderBinaryOutputStore,
    registry: InMemoryProviderRegistry,
    profile_routes: dict[str, set[str]],
    registered_keys: set[str],
) -> int:
    if config["provider"] != "openai":
        raise ModelGatewayBootstrapError("unsupported media provider kind")
    api_key = _required_string(config, "api_key", max_length=8192)
    organization = _optional_string(config.get("organization"), max_length=512)
    project = _optional_string(config.get("project"), max_length=512)
    timeout_seconds = _timeout_seconds(config.get("timeout_seconds", 180), maximum=600)
    models = config["image_models"]
    assert isinstance(models, list)
    for raw_model in models:
        if not isinstance(raw_model, dict):
            raise ModelGatewayBootstrapError("image model config must be an object")
        _reject_unknown_keys(
            raw_model,
            {"name", "profiles", "quality_score", "price"},
            scope="image_model",
        )
        model = _required_string(raw_model, "name", max_length=255)
        profiles = _required_profiles(raw_model)
        quality_score = raw_model.get("quality_score", 92)
        if (
            isinstance(quality_score, bool)
            or not isinstance(quality_score, int)
            or not 0 <= quality_score <= 100
        ):
            raise ModelGatewayBootstrapError("image model quality_score must be 0..100")
        raw_price = raw_model.get("price")
        if not isinstance(raw_price, dict):
            raise ModelGatewayBootstrapError(
                f"image price config is required for model {model}"
            )
        _reject_unknown_keys(
            raw_price,
            {
                "snapshot_id",
                "max_estimated_request_usd",
                "text_input_usd_per_million_tokens",
                "image_input_usd_per_million_tokens",
                "image_output_usd_per_million_tokens",
            },
            scope=f"image_price:{model}",
        )
        adapter = OpenAIImageGenerationAdapter(
            api_key=api_key,
            model=model,
            price_card=OpenAIImagePriceCard(
                snapshot_id=_required_string(raw_price, "snapshot_id", max_length=128),
                max_estimated_request_usd=_required_positive_money_decimal(
                    raw_price,
                    "max_estimated_request_usd",
                ),
                text_input_usd_per_million_tokens=_required_money_decimal(
                    raw_price,
                    "text_input_usd_per_million_tokens",
                ),
                image_input_usd_per_million_tokens=_required_money_decimal(
                    raw_price,
                    "image_input_usd_per_million_tokens",
                ),
                image_output_usd_per_million_tokens=_required_money_decimal(
                    raw_price,
                    "image_output_usd_per_million_tokens",
                ),
            ),
            output_store=output_store,
            organization=organization,
            project=project,
            timeout_seconds=timeout_seconds,
            quality_score=quality_score,
        )
        _register_adapter(
            adapter=adapter,
            profiles=profiles,
            registry=registry,
            profile_routes=profile_routes,
            registered_keys=registered_keys,
        )
    return len(models)


def _register_adapter(
    *,
    adapter: Any,
    profiles: tuple[str, ...],
    registry: InMemoryProviderRegistry,
    profile_routes: dict[str, set[str]],
    registered_keys: set[str],
) -> None:
    key = adapter.descriptor.key
    if key in registered_keys:
        raise ModelGatewayBootstrapError(f"duplicate hosted provider model key: {key}")
    registry.register(adapter)
    registered_keys.add(key)
    for profile in profiles:
        profile_routes.setdefault(profile, set()).add(key)


def _parse_provider_secret(raw: str) -> dict[str, Any]:
    payload = _parse_secret_object(raw, label="model provider")
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
    _validate_model_names_and_profiles(models, label="provider model")
    return payload


def _parse_media_provider_secret(raw: str) -> dict[str, Any]:
    payload = _parse_secret_object(raw, label="media provider")
    _reject_unknown_keys(
        payload,
        {
            "schema_version",
            "provider",
            "api_key",
            "organization",
            "project",
            "timeout_seconds",
            "image_models",
        },
        scope="media_root",
    )
    if payload.get("schema_version") != _MEDIA_PROVIDER_SECRET_SCHEMA_VERSION:
        raise ModelGatewayBootstrapError("unsupported media provider secret schema version")
    provider = _required_string(payload, "provider", max_length=100)
    if provider != "openai":
        raise ModelGatewayBootstrapError("only the openai hosted media adapter is enabled")
    _required_string(payload, "api_key", max_length=8192)
    models = payload.get("image_models")
    if not isinstance(models, list) or not 1 <= len(models) <= _MAX_MODELS:
        raise ModelGatewayBootstrapError("media provider secret requires 1..32 image_models")
    _validate_model_names_and_profiles(models, label="image model")
    return payload


def _parse_secret_object(raw: str, *, label: str) -> dict[str, Any]:
    if not raw or len(raw) > 262_144:
        raise ModelGatewayBootstrapError(f"{label} secret is missing or too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelGatewayBootstrapError(f"{label} secret must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelGatewayBootstrapError(f"{label} secret must be a JSON object")
    return payload


def _validate_model_names_and_profiles(models: list[Any], *, label: str) -> None:
    names: set[str] = set()
    all_profiles: set[str] = set()
    for raw_model in models:
        if not isinstance(raw_model, dict):
            raise ModelGatewayBootstrapError(f"{label} config must be an object")
        name = _required_string(raw_model, "name", max_length=255)
        if name in names:
            raise ModelGatewayBootstrapError(f"duplicate {label}: {name}")
        names.add(name)
        all_profiles.update(_required_profiles(raw_model))
    if not all_profiles:
        raise ModelGatewayBootstrapError(f"at least one logical {label} profile is required")


def _required_profiles(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("profiles")
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_PROFILES_PER_MODEL:
        raise ModelGatewayBootstrapError("model profiles must contain 1..16 values")
    profiles: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not _PROFILE.fullmatch(item):
            raise ModelGatewayBootstrapError("invalid model profile")
        if item in profiles:
            raise ModelGatewayBootstrapError(f"duplicate model profile: {item}")
        profiles.append(item)
    return tuple(profiles)


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


def _required_positive_money_decimal(payload: dict[str, Any], key: str) -> Decimal:
    value = _required_money_decimal(payload, key)
    if value <= 0:
        raise ModelGatewayBootstrapError(f"{key} must be greater than zero")
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


def _timeout_seconds(value: Any, *, maximum: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelGatewayBootstrapError("provider timeout_seconds must be numeric")
    timeout = float(value)
    if not 1 <= timeout <= maximum:
        raise ModelGatewayBootstrapError(
            f"provider timeout_seconds must be within 1..{maximum}"
        )
    return timeout


def _reject_unknown_keys(payload: dict[str, Any], allowed: set[str], *, scope: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ModelGatewayBootstrapError(
            f"unknown {scope} provider config fields: {','.join(sorted(unknown))}"
        )

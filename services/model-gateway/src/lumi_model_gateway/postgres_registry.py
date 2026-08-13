from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from .capability_registry import (
    BenchmarkScore,
    CapabilityClaim,
    EvidenceConfidence,
    PricingSnapshot,
    RegistryModelSnapshot,
    RegistryOrganizationPolicy,
    RegistrySnapshot,
    RoutingProfile,
    SupportLevel,
)
from .models import Capability


class RegistryReadConnection(Protocol):
    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, Any] | None: ...

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, Any]]: ...


class PostgresRegistryLoader:
    """Builds an immutable RegistrySnapshot from a PostgreSQL-compatible read port."""

    async def load_active(
        self,
        connection: RegistryReadConnection,
        *,
        organization_ids: tuple[UUID, ...] = (),
        at_time: datetime | None = None,
    ) -> RegistrySnapshot:
        effective_at = _utc(at_time or datetime.now(UTC))
        version = await connection.fetchrow(
            """
            SELECT id, version, source_registry_version, content_hash,
                   observed_at, source_ref
            FROM model_registry_versions
            WHERE activated_at IS NOT NULL
            ORDER BY activated_at DESC, version DESC
            LIMIT 1
            """
        )
        if version is None:
            raise RuntimeError("MODEL_REGISTRY_ACTIVE_VERSION_NOT_FOUND")
        version_id = _uuid(version["id"])
        models = await connection.fetch(
            """
            SELECT model_key, provider, model, lifecycle, route_eligible,
                   regions_json, latency_class, benchmark_status,
                   observed_at, source_ref
            FROM model_registry_models
            WHERE registry_version_id = $1
            ORDER BY model_key
            """,
            version_id,
        )
        claims = await connection.fetch(
            """
            SELECT model_key, capability, support, limits_json, confidence,
                   observed_at, source_ref
            FROM model_capability_claims
            WHERE registry_version_id = $1
            ORDER BY model_key, capability
            """,
            version_id,
        )
        pricing = await connection.fetch(
            """
            SELECT price_snapshot_key, model_key, currency, unit, price,
                   minimum_charge, effective_from, valid_until,
                   observed_at, source_ref
            FROM model_pricing_snapshots
            WHERE registry_version_id = $1
            ORDER BY model_key, unit, effective_from
            """,
            version_id,
        )
        benchmarks = await connection.fetch(
            """
            SELECT model_key, profile, score, dataset_version, run_id,
                   sample_count, statistics_json, confidence,
                   observed_at, source_ref
            FROM model_benchmark_scores
            WHERE registry_version_id = $1
            ORDER BY model_key, profile, observed_at, run_id
            """,
            version_id,
        )
        profiles = await connection.fetch(
            """
            SELECT profile, required_capabilities_json, candidate_models_json,
                   weights_json, minimum_json, observed_at, source_ref
            FROM model_routing_profiles
            WHERE registry_version_id = $1
            ORDER BY profile
            """,
            version_id,
        )
        policies: Sequence[Mapping[str, Any]] = ()
        if organization_ids:
            policies = await connection.fetch(
                """
                SELECT organization_id, policy_version, disabled_providers_json,
                       denied_models_json, allowed_regions_json, max_cost_class,
                       preferred_models_json, data_handling_restrictions_json,
                       effective_from, effective_to
                FROM organization_model_policies
                WHERE organization_id = ANY($1::uuid[])
                  AND effective_from <= $2
                  AND (effective_to IS NULL OR $2 < effective_to)
                ORDER BY organization_id, policy_version
                """,
                list(organization_ids),
                effective_at,
            )
        return RegistrySnapshot(
            snapshot_id=version_id,
            registry_version=int(version["version"]),
            source_registry_version=str(version["source_registry_version"]),
            content_hash=str(version["content_hash"]),
            observed_at=_datetime(version["observed_at"]),
            source_ref=str(version["source_ref"]),
            models=tuple(_model(row) for row in models),
            capability_claims=tuple(_claim(row) for row in claims),
            pricing=tuple(_price(row) for row in pricing),
            benchmarks=tuple(_benchmark(row) for row in benchmarks),
            routing_profiles=tuple(_profile(row) for row in profiles),
            organization_policies=tuple(_policy(row) for row in policies),
        )


def _model(row: Mapping[str, Any]) -> RegistryModelSnapshot:
    return RegistryModelSnapshot(
        model_key=str(row["model_key"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        lifecycle=str(row["lifecycle"]),
        route_eligible=bool(row["route_eligible"]),
        regions=tuple(_json_list(row["regions_json"])),
        latency_class=(
            str(row["latency_class"]) if row["latency_class"] is not None else None
        ),
        benchmark_status=str(row["benchmark_status"]),
        observed_at=_datetime(row["observed_at"]),
        source_ref=str(row["source_ref"]),
    )


def _claim(row: Mapping[str, Any]) -> CapabilityClaim:
    return CapabilityClaim(
        model_key=str(row["model_key"]),
        capability=Capability(str(row["capability"])),
        support=SupportLevel(str(row["support"])),
        limits_json=_canonical_json(_json_dict(row["limits_json"])),
        confidence=EvidenceConfidence(str(row["confidence"])),
        observed_at=_datetime(row["observed_at"]),
        source_ref=str(row["source_ref"]),
    )


def _price(row: Mapping[str, Any]) -> PricingSnapshot:
    return PricingSnapshot(
        price_snapshot_id=str(row["price_snapshot_key"]),
        model_key=str(row["model_key"]),
        currency=str(row["currency"]),
        unit=str(row["unit"]),
        price=Decimal(str(row["price"])),
        minimum_charge=(
            Decimal(str(row["minimum_charge"]))
            if row["minimum_charge"] is not None
            else None
        ),
        effective_from=_datetime(row["effective_from"]),
        valid_until=(
            _datetime(row["valid_until"])
            if row["valid_until"] is not None
            else None
        ),
        observed_at=_datetime(row["observed_at"]),
        source_ref=str(row["source_ref"]),
    )


def _benchmark(row: Mapping[str, Any]) -> BenchmarkScore:
    return BenchmarkScore(
        model_key=str(row["model_key"]),
        profile=str(row["profile"]),
        score=Decimal(str(row["score"])),
        dataset_version=str(row["dataset_version"]),
        run_id=str(row["run_id"]),
        sample_count=int(row["sample_count"]),
        statistics_json=_canonical_json(_json_dict(row["statistics_json"])),
        confidence=EvidenceConfidence(str(row["confidence"])),
        observed_at=_datetime(row["observed_at"]),
        source_ref=str(row["source_ref"]),
    )


def _profile(row: Mapping[str, Any]) -> RoutingProfile:
    required = tuple(
        Capability(str(item))
        for item in _json_list(row["required_capabilities_json"])
    )
    return RoutingProfile(
        profile=str(row["profile"]),
        required_capabilities=required,
        candidate_models=tuple(_json_list(row["candidate_models_json"])),
        weights_json=_canonical_json(_json_dict(row["weights_json"])),
        minimum_json=_canonical_json(_json_dict(row["minimum_json"])),
        observed_at=_datetime(row["observed_at"]),
        source_ref=str(row["source_ref"]),
    )


def _policy(row: Mapping[str, Any]) -> RegistryOrganizationPolicy:
    return RegistryOrganizationPolicy(
        organization_id=_uuid(row["organization_id"]),
        policy_version=int(row["policy_version"]),
        disabled_providers=frozenset(_json_list(row["disabled_providers_json"])),
        denied_models=frozenset(_json_list(row["denied_models_json"])),
        allowed_regions=frozenset(_json_list(row["allowed_regions_json"])),
        max_cost_class=(
            str(row["max_cost_class"]) if row["max_cost_class"] is not None else None
        ),
        preferred_models=tuple(_json_list(row["preferred_models_json"])),
        data_handling_restrictions=tuple(
            _json_list(row["data_handling_restrictions_json"])
        ),
    )


def _json_list(value: Any) -> list[str]:
    parsed = _json_value(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError("MODEL_REGISTRY_JSON_LIST_INVALID")
    return list(parsed)


def _json_dict(value: Any) -> dict[str, Any]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_REGISTRY_JSON_OBJECT_INVALID")
    return dict(parsed)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("MODEL_REGISTRY_DATETIME_INVALID")
    return _utc(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("MODEL_REGISTRY_NAIVE_DATETIME")
    return value.astimezone(UTC)

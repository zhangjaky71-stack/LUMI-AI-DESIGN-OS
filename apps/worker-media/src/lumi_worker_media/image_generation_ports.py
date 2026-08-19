from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Mapping, cast
from uuid import UUID, uuid5

import asyncpg
from lumi_asset_storage.s3 import S3ObjectStore
from lumi_image_generation.asset_intelligence_adapter import ReferenceAuthorizationError
from lumi_image_generation.model import (
    AuthorizedReference,
    ImageGenerationSpec,
    ImageReference,
    Rights,
    StoredImage,
    ValidatedImage,
)

_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_ALLOWED_RIGHTS_REVIEWS = frozenset({"ASSERTED", "VERIFIED"})


class PostgresReferenceAuthorizer:
    """Fail-closed reference authorization over canonical Asset/AssetRights rows."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

    async def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]:
        if not references:
            return ()
        connection = await asyncpg.connect(self.dsn)
        try:
            authorized: list[AuthorizedReference] = []
            for reference in references:
                row = await connection.fetchrow(
                    """
                    SELECT
                        a.id AS asset_id,
                        a.project_id,
                        a.status,
                        a.deleted_at,
                        af.variant,
                        af.checksum_sha256,
                        af.mime_type,
                        ar.source_type,
                        ar.license_type,
                        ar.commercial_use,
                        ar.review_status,
                        ar.expires_at
                    FROM assets a
                    JOIN asset_files af
                      ON af.organization_id = a.organization_id
                     AND af.asset_id = a.id
                     AND af.variant = $4
                    LEFT JOIN asset_rights ar
                      ON ar.organization_id = a.organization_id
                     AND ar.asset_id = a.id
                    WHERE a.organization_id = $1
                      AND a.project_id = $2
                      AND a.id = $3
                    """,
                    UUID(spec.organization_id),
                    UUID(spec.project_id),
                    UUID(reference.asset_id),
                    reference.asset_version,
                )
                if row is None:
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_NOT_ACCESSIBLE:{reference.asset_id}@{reference.asset_version}"
                    )
                if row["status"] != "ready" or row["deleted_at"] is not None:
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_NOT_READY:{reference.asset_id}@{reference.asset_version}"
                    )
                if row["source_type"] is None:
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_RIGHTS_MISSING:{reference.asset_id}@{reference.asset_version}"
                    )
                review_status = str(row["review_status"])
                if review_status not in _ALLOWED_RIGHTS_REVIEWS:
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_RIGHTS_UNVERIFIED:{reference.asset_id}@{reference.asset_version}"
                    )
                expires_at = row["expires_at"]
                if expires_at is not None and expires_at <= datetime.now(UTC):
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_RIGHTS_EXPIRED:{reference.asset_id}@{reference.asset_version}"
                    )
                if row["commercial_use"] != "ALLOWED":
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_COMMERCIAL_USE_FORBIDDEN:{reference.asset_id}@{reference.asset_version}"
                    )
                rights = _rights_kind(str(row["source_type"]), row["license_type"])
                if rights == "UNKNOWN":
                    raise ReferenceAuthorizationError(
                        f"GENERATION_REFERENCE_RIGHTS_UNKNOWN:{reference.asset_id}@{reference.asset_version}"
                    )
                authorized.append(
                    AuthorizedReference(
                        asset_id=str(row["asset_id"]),
                        asset_version=str(row["variant"]),
                        role=reference.role,
                        source=reference.source,
                        durable_ref=f"asset:{row['asset_id']}@{row['variant']}",
                        rights=cast(Rights, rights),
                        commercial_use_allowed=True,
                        checksum_sha256=str(row["checksum_sha256"]),
                        mime_type=str(row["mime_type"]),
                        approval_state=review_status,
                    )
                )
            return tuple(authorized)
        finally:
            await connection.close()


class S3GeneratedImageStore:
    """Moves validated provider bytes into the durable generated-asset namespace."""

    def __init__(
        self,
        *,
        bucket: str,
        object_store: S3ObjectStore,
        max_bytes: int = _MAX_IMAGE_BYTES,
    ) -> None:
        if not bucket or "/" in bucket or bucket != bucket.strip():
            raise ValueError("GENERATED_IMAGE_BUCKET_INVALID")
        if not 1 <= max_bytes <= _MAX_IMAGE_BYTES:
            raise ValueError("GENERATED_IMAGE_MAX_BYTES_INVALID")
        self.bucket = bucket
        self.object_store = object_store
        self.max_bytes = max_bytes

    @classmethod
    def from_env(cls) -> S3GeneratedImageStore:
        bucket = _required_env("LUMI_S3_BUCKET", max_length=255)
        region = os.getenv("LUMI_S3_REGION") or os.getenv("AWS_REGION") or "us-east-1"
        return cls(
            bucket=bucket,
            object_store=S3ObjectStore(
                endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL"),
                region_name=region,
                access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY"),
                force_path_style=_env_bool("LUMI_S3_FORCE_PATH_STYLE"),
            ),
        )

    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
    ) -> StoredImage:
        if hashlib.sha256(image.content).hexdigest() != image.checksum_sha256:
            raise ValueError("GENERATION_STORAGE_CHECKSUM_MISMATCH")
        extension = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
        }.get(image.mime_type)
        if extension is None:
            raise ValueError("GENERATION_STORAGE_MIME_UNSUPPORTED")
        safe_candidate = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
        object_key = (
            f"generated/v1/{spec.organization_id}/{spec.project_id}/"
            f"{safe_candidate}/{image.checksum_sha256}.{extension}"
        )
        await self.object_store.put_bytes(
            bucket=self.bucket,
            object_key=object_key,
            data=image.content,
            content_type=image.mime_type,
            max_bytes=self.max_bytes,
            metadata={
                "lumi-generation-operation": spec.operation_id,
                "lumi-checksum-sha256": image.checksum_sha256,
            },
        )
        return StoredImage(
            storage_key=object_key,
            mime_type=image.mime_type,
            width=image.width,
            height=image.height,
            size_bytes=len(image.content),
            checksum_sha256=image.checksum_sha256,
        )


class PostgresGenerationCostObserver:
    """Verifies NODE-27 provider cost already exists; never writes a second charge."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

    async def record_generation_result(
        self,
        *,
        generation_id: str,
        candidate_id: str,
        operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> None:
        del candidate_id
        connection = await asyncpg.connect(self.dsn)
        try:
            org_id = await connection.fetchval(
                """
                SELECT organization_id
                FROM generations
                WHERE result_json -> 'job' ->> 'generation_id' = $1
                ORDER BY created_at, id
                LIMIT 1
                """,
                generation_id,
            )
            if org_id is None:
                raise RuntimeError("GENERATION_COST_SCOPE_NOT_FOUND")
            rows = await connection.fetch(
                """
                SELECT
                    cl.amount,
                    cl.confidence,
                    cl.pricing_snapshot_id,
                    cl.external_provider_request_id
                FROM cost_ledger cl
                JOIN idempotency_operations io ON io.id = cl.operation_id
                WHERE cl.organization_id = $1
                  AND io.organization_id = $1
                  AND io.operation_type = 'paid_model_invocation'
                  AND io.business_scope_id = $2
                  AND cl.entry_type = 'actual_cost'
                  AND cl.cost_basis = 'provider_cost'
                  AND cl.provider = $3
                  AND cl.model = $4
                ORDER BY cl.occurred_at, cl.id
                LIMIT 2
                """,
                org_id,
                UUID(operation_id),
                provider,
                model,
            )
            if len(rows) != 1:
                raise RuntimeError("GENERATION_COST_LEDGER_ENTRY_NOT_UNIQUE")
            row = rows[0]
            if provider_request_id and row["external_provider_request_id"] != provider_request_id:
                raise RuntimeError("GENERATION_COST_PROVIDER_REQUEST_MISMATCH")
            if amount_usd is not None and Decimal(row["amount"]) != amount_usd:
                raise RuntimeError("GENERATION_COST_AMOUNT_MISMATCH")
            if str(row["confidence"]) != confidence:
                raise RuntimeError("GENERATION_COST_CONFIDENCE_MISMATCH")
            if (
                pricing_snapshot_id is not None
                and row["pricing_snapshot_id"] != pricing_snapshot_id
            ):
                raise RuntimeError("GENERATION_COST_PRICE_SNAPSHOT_MISMATCH")
        finally:
            await connection.close()


class PostgresGenerationEventSink:
    """Appends idempotent domain events to the canonical outbox table."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        generation_id: str,
        payload: Mapping[str, object],
    ) -> None:
        if not event_type or len(event_type) > 100:
            raise ValueError("GENERATION_EVENT_TYPE_INVALID")
        normalized = _json_value(dict(payload))
        if not isinstance(normalized, dict):
            raise ValueError("GENERATION_EVENT_PAYLOAD_INVALID")
        normalized = {"generation_id": generation_id, **normalized}
        aggregate_id = uuid5(UUID(organization_id), generation_id)
        event_hash = hashlib.sha256(
            json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        event_id = uuid5(
            aggregate_id,
            f"node46:{event_type}:{event_hash}",
        )
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                INSERT INTO outbox_events (
                    id, organization_id, aggregate_type, aggregate_id,
                    event_type, event_version, payload_json, occurred_at,
                    publish_attempts
                ) VALUES (
                    $1,$2,'generation',$3,$4,1,$5::jsonb,now(),0
                )
                ON CONFLICT (id) DO NOTHING
                """,
                event_id,
                UUID(organization_id),
                aggregate_id,
                event_type,
                json.dumps(normalized, ensure_ascii=False, sort_keys=True),
            )
        finally:
            await connection.close()


def _rights_kind(source_type: str, license_type: object) -> str:
    if source_type == "USER_UPLOAD" or license_type == "OWNED":
        return "USER_OWNED"
    if source_type in {"LICENSED", "STOCK_PROVIDER"} or license_type in {
        "COMMERCIAL_LICENSE",
        "PUBLIC_DOMAIN",
        "CC0",
        "CC_BY",
        "CC_BY_SA",
    }:
        return "LICENSED"
    return "UNKNOWN"


def _json_value(value: object, *, depth: int = 0) -> object:
    if depth > 16:
        raise ValueError("GENERATION_EVENT_PAYLOAD_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("GENERATION_EVENT_NON_FINITE_FLOAT")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("GENERATION_EVENT_NON_FINITE_DECIMAL")
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("GENERATION_EVENT_KEY_INVALID")
        return {
            key: _json_value(item, depth=depth + 1)
            for key, item in sorted(value.items())
        }
    raise ValueError(f"GENERATION_EVENT_VALUE_INVALID:{type(value).__name__}")


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _env_bool(name: str) -> bool:
    value = os.getenv(name, "").strip().casefold()
    if not value:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name}_INVALID")


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("GENERATION_DATABASE_URL_MUST_USE_POSTGRESQL")

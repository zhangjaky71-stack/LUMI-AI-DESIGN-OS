from __future__ import annotations

from typing import Any

from lumi_api.assets.models import AssetEvent, AssetEventType, AssetRecord
from lumi_api.projects.models import ProjectEvent, ProjectEventType, ProjectRecord

from .envelope import EventEnvelope, new_event
from .payloads import AssetReadyV1, ProjectCreatedV1


def project_created_envelope(
    project: ProjectRecord,
    event: ProjectEvent,
    *,
    producer: str = "lumi.api",
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> EventEnvelope[ProjectCreatedV1]:
    if event.event_type is not ProjectEventType.CREATED:
        raise ValueError("PROJECT_EVENT_NOT_CREATED")
    if (
        event.organization_id != project.organization_id
        or event.project_id != project.id
    ):
        raise ValueError("PROJECT_EVENT_AGGREGATE_MISMATCH")
    return new_event(
        event_id=event.id,
        event_type="lumi.project.created.v1",
        occurred_at=event.occurred_at,
        organization_id=project.organization_id,
        aggregate_type="project",
        aggregate_id=project.id,
        aggregate_version=project.version,
        producer=producer,
        correlation_id=correlation_id,
        traceparent=traceparent,
        payload=ProjectCreatedV1(
            project_id=project.id,
            workspace_id=project.workspace_id,
            project_version=project.version,
        ),
    )


def asset_ready_envelope(
    asset: AssetRecord,
    event: AssetEvent,
    *,
    checksum_sha256: str,
    producer: str = "lumi.worker-media",
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> EventEnvelope[AssetReadyV1]:
    if event.event_type is not AssetEventType.READY:
        raise ValueError("ASSET_EVENT_NOT_READY")
    if (
        event.organization_id != asset.organization_id
        or event.project_id != asset.project_id
        or event.asset_id != asset.id
    ):
        raise ValueError("ASSET_EVENT_AGGREGATE_MISMATCH")
    if not asset.mime_type:
        raise ValueError("ASSET_VERIFIED_MIME_REQUIRED")
    return new_event(
        event_id=event.id,
        event_type="lumi.asset.ready.v1",
        occurred_at=event.occurred_at,
        organization_id=asset.organization_id,
        aggregate_type="asset",
        aggregate_id=asset.id,
        producer=producer,
        correlation_id=correlation_id,
        traceparent=traceparent,
        payload=AssetReadyV1(
            asset_id=asset.id,
            project_id=asset.project_id,
            mime_type=asset.mime_type,
            checksum_sha256=checksum_sha256,
        ),
    )


def outbox_row(envelope: EventEnvelope[Any]) -> dict[str, Any]:
    """Persistence-ready row whose payload_json is the immutable canonical envelope."""

    return {
        "id": envelope.event_id,
        "organization_id": envelope.organization_id,
        "event_type": envelope.event_type,
        "aggregate_type": envelope.aggregate_type,
        "aggregate_id": envelope.aggregate_id,
        "payload_json": envelope.model_dump(mode="json"),
        "occurred_at": envelope.occurred_at,
    }

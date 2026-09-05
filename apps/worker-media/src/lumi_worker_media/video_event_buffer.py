from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

import asyncpg

from .video_generation_ports import _asyncpg_dsn, _json_value


@dataclass(frozen=True, slots=True)
class BufferedVideoEvent:
    event_id: UUID
    organization_id: UUID
    event_type: str
    aggregate_id: UUID
    payload_json: str


class BufferedVideoEventSink:
    """Invocation-local EventPort whose rows commit with the Hosted video snapshot UoW."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)
        self._pending: dict[UUID, BufferedVideoEvent] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        video_job_id: str,
        payload: Mapping[str, object],
    ) -> None:
        if not event_type.startswith("video_generation.") or len(event_type) > 150:
            raise ValueError("VIDEO_EVENT_TYPE_INVALID")
        if not video_job_id or len(video_job_id) > 512 or "\x00" in video_job_id:
            raise ValueError("VIDEO_EVENT_JOB_ID_INVALID")
        normalized = _json_value(dict(payload))
        if not isinstance(normalized, dict):
            raise ValueError("VIDEO_EVENT_PAYLOAD_INVALID")
        organization_uuid = UUID(organization_id)
        aggregate_id = uuid5(organization_uuid, video_job_id)
        event_payload = {
            "video_job_id": video_job_id,
            **normalized,
        }
        payload_json = json.dumps(
            event_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_id = uuid5(aggregate_id, f"node48:{event_type}:{digest}")
        event = BufferedVideoEvent(
            event_id=event_id,
            organization_id=organization_uuid,
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload_json=payload_json,
        )
        existing = self._pending.get(event_id)
        if existing is not None and existing != event:
            raise RuntimeError("VIDEO_EVENT_IDENTITY_CONFLICT")
        self._pending[event_id] = event

    async def flush_into(self, connection: asyncpg.Connection) -> None:
        """Stage buffered rows on an existing transaction; caller owns commit/rollback."""

        for event in self._pending.values():
            await connection.execute(
                """
                INSERT INTO outbox_events (
                    id, organization_id, event_name, aggregate_type, aggregate_id,
                    schema_version, payload_json, published_at, publish_attempts,
                    created_at
                ) VALUES (
                    $1,$2,$3,'video_generation',$4,1,$5::jsonb,NULL,0,now()
                )
                ON CONFLICT (id) DO NOTHING
                """,
                event.event_id,
                event.organization_id,
                event.event_type,
                event.aggregate_id,
                event.payload_json,
            )

    def mark_committed(self) -> None:
        self._pending.clear()


__all__ = ["BufferedVideoEvent", "BufferedVideoEventSink"]

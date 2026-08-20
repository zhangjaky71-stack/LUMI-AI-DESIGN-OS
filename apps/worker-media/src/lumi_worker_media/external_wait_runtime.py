from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid5

import asyncpg
from lumi_domain.job_dispatch import JOB_DISPATCH_EVENT_NAME, JOB_DISPATCH_SCHEMA_VERSION

from .job_dispatch_runtime import MediaJobOutboxRecord


@dataclass(frozen=True, slots=True)
class ExternalWaitWake:
    task_id: UUID
    organization_id: UUID
    project_id: UUID
    state_version: int
    event_id: UUID


class MediaExternalWaitWakeScheduler:
    """Stage durable redispatch for due external waits without consuming retry budget.

    The scheduler never reconstructs a business message. It copies the task's most
    recent already-validated canonical `job.dispatch.requested` payload, validates
    it again against the locked task scope, writes a new idempotent outbox event,
    then clears retry_not_before. The task remains `waiting_external` until Worker
    claim atomically transitions it back to `running` without incrementing attempts.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def stage_due_batch(self, *, limit: int = 100) -> tuple[ExternalWaitWake, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("EXTERNAL_WAIT_WAKE_BATCH_LIMIT_INVALID")
        connection = await asyncpg.connect(self.dsn)
        wakes: list[ExternalWaitWake] = []
        try:
            async with connection.transaction():
                tasks = await connection.fetch(
                    """
                    SELECT id, organization_id, project_id, state_version
                    FROM tasks
                    WHERE status = 'waiting_external'
                      AND retry_not_before IS NOT NULL
                      AND retry_not_before <= now()
                    ORDER BY retry_not_before, priority, created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                    """,
                    limit,
                )
                for task in tasks:
                    dispatch_row = await connection.fetchrow(
                        """
                        SELECT id, schema_version, payload_json
                        FROM outbox_events
                        WHERE organization_id = $1
                          AND aggregate_type = 'task'
                          AND aggregate_id = $2
                          AND event_name = $3
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """,
                        task["organization_id"],
                        task["id"],
                        JOB_DISPATCH_EVENT_NAME,
                    )
                    if dispatch_row is None:
                        raise RuntimeError("EXTERNAL_WAIT_CANONICAL_DISPATCH_MISSING")
                    record = MediaJobOutboxRecord(
                        event_id=dispatch_row["id"],
                        organization_id=task["organization_id"],
                        aggregate_type="task",
                        aggregate_id=task["id"],
                        schema_version=int(dispatch_row["schema_version"]),
                        payload=dict(dispatch_row["payload_json"]),
                    )
                    dispatch = record.dispatch()
                    if dispatch.message.project_id != task["project_id"]:
                        raise RuntimeError("EXTERNAL_WAIT_DISPATCH_PROJECT_MISMATCH")

                    next_state_version = int(task["state_version"]) + 1
                    event_id = uuid5(
                        task["id"],
                        f"lumi:external-wake:{next_state_version}",
                    )
                    await connection.execute(
                        """
                        INSERT INTO outbox_events (
                            id, organization_id, event_name, aggregate_type,
                            aggregate_id, schema_version, payload_json,
                            publish_attempts, created_at
                        ) VALUES ($1,$2,$3,'task',$4,$5,$6::jsonb,0,now())
                        ON CONFLICT (id) DO NOTHING
                        """,
                        event_id,
                        task["organization_id"],
                        JOB_DISPATCH_EVENT_NAME,
                        task["id"],
                        JOB_DISPATCH_SCHEMA_VERSION,
                        json.dumps(
                            dispatch.as_outbox_payload(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                    updated = await connection.execute(
                        """
                        UPDATE tasks
                        SET retry_not_before = NULL,
                            updated_at = now(),
                            state_version = $4,
                            version = version + 1
                        WHERE id = $1
                          AND organization_id = $2
                          AND project_id = $3
                          AND status = 'waiting_external'
                          AND retry_not_before IS NOT NULL
                        """,
                        task["id"],
                        task["organization_id"],
                        task["project_id"],
                        next_state_version,
                    )
                    if updated != "UPDATE 1":
                        raise RuntimeError("EXTERNAL_WAIT_WAKE_STATE_CONFLICT")
                    wakes.append(
                        ExternalWaitWake(
                            task_id=task["id"],
                            organization_id=task["organization_id"],
                            project_id=task["project_id"],
                            state_version=next_state_version,
                            event_id=event_id,
                        )
                    )
            return tuple(wakes)
        finally:
            await connection.close()

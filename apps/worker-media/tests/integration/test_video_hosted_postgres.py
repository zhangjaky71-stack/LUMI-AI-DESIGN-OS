from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_domain.job_dispatch import (
    JOB_DISPATCH_EVENT_NAME,
    JOB_DISPATCH_SCHEMA_VERSION,
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_TASK_NAME,
    JobDispatch,
    JobMessage,
)
from lumi_video_generation.model import (
    CompiledShot,
    FinalVideoProvenance,
    GatewayVideoResult,
    ProviderJobRecord,
    RenderedVideo,
    ShotProvenance,
    ShotRuntime,
    ShotSpec,
    ShotValidationReport,
    StoredVideoClip,
    VideoJob,
    VideoTaskSpec,
)
from lumi_worker_media.external_wait_runtime import MediaExternalWaitWakeScheduler
from lumi_worker_media.job_runtime import ExternalWait, TaskJobStore, execute_job
from lumi_worker_media.queue_contracts import JobState
from lumi_worker_media.video_cost_runtime import ScopedPostgresVideoCostObserver
from lumi_worker_media.video_generation_artifacts import PostgresVideoArtifactAdapter
from lumi_worker_media.video_generation_ports import PostgresVideoEventSink
from lumi_worker_media.video_generation_repository import PostgresVideoRepository

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated and seeded local PostgreSQL",
)

ORG = "01900000-0000-7000-8000-000000000001"
PROJECT = "01900000-0000-7000-8000-000000000006"
TASK = "73900000-0000-7000-8000-000000000001"
OPERATION = "73900000-0000-7000-8000-000000000002"
PAID_OPERATION = "73900000-0000-7000-8000-000000000003"
IDEMPOTENCY_OPERATION = "73900000-0000-7000-8000-000000000004"
VIDEO_JOB_ID = "video-job:" + "a" * 64
SHOT_ID = "hero"
STORYBOARD_HASH = "b" * 64
REQUEST_HASH = "c" * 64
CLIP_CHECKSUM = "d" * 64
FINAL_CHECKSUM = "e" * 64
PROVIDER_REQUEST_ID = "video_pg_provider_001"


def _dsn() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _migration_dsn() -> str:
    value = os.environ.get("MIGRATION_DATABASE_URL", os.environ["DATABASE_URL"])
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _spec() -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        mode="TEXT_TO_VIDEO",
        prompt="A minimal studio product reveal",
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("5.00"),
        code_git_sha="1" * 40,
        shots=(
            ShotSpec(
                shot_id=SHOT_ID,
                duration_seconds=Decimal("4"),
                prompt="Slow cinematic reveal",
            ),
        ),
        recipe_version="postgres-video-v1",
    )


def _job(spec: VideoTaskSpec) -> VideoJob:
    return VideoJob(
        video_job_id=VIDEO_JOB_ID,
        organization_id=ORG,
        operation_id=OPERATION,
        semantic_hash=spec.semantic_hash,
        storyboard_hash=STORYBOARD_HASH,
        status="WAITING_EXTERNAL",
        shots=(
            ShotRuntime(
                shot_id=SHOT_ID,
                ordinal=1,
                paid_operation_id=PAID_OPERATION,
                status="WAITING_EXTERNAL",
                attempt_count=1,
                provider="openai",
                model="sora-2",
                provider_request_id=PROVIDER_REQUEST_ID,
            ),
        ),
        estimated_cost_usd=Decimal("1.25000000"),
    )


def _provider_record() -> ProviderJobRecord:
    return ProviderJobRecord(
        organization_id=ORG,
        video_job_id=VIDEO_JOB_ID,
        shot_id=SHOT_ID,
        paid_operation_id=PAID_OPERATION,
        request_hash=REQUEST_HASH,
        result=GatewayVideoResult(
            status="PENDING",
            provider="openai",
            model="sora-2",
            provider_request_id=PROVIDER_REQUEST_ID,
            output_ref=None,
            output_mime_type=None,
            cost_usd=Decimal("1.25000000"),
            cost_confidence="estimated",
            pricing_snapshot_id="sora-price-v1",
            routing_reason_codes=("PROFILE_MATCH",),
        ),
    )


def _compiled_shot() -> CompiledShot:
    return CompiledShot(
        shot=_spec().shots[0],
        paid_operation_id=PAID_OPERATION,
        ordinal=1,
    )


def _clip() -> StoredVideoClip:
    key = f"generated/video/v1/{ORG}/{PROJECT}/shots/{SHOT_ID}/{CLIP_CHECKSUM}.mp4"
    return StoredVideoClip(
        storage_key=key,
        checksum_sha256=CLIP_CHECKSUM,
        mime_type="video/mp4",
        size_bytes=4096,
        width=1280,
        height=720,
        duration_ms=4000,
        durable_asset_ref=key,
        poster_frame_ref=None,
        tail_frame_ref=None,
        keyframe_refs=(),
    )


def _final_clip() -> StoredVideoClip:
    key = f"generated/video/v1/{ORG}/{PROJECT}/final/{FINAL_CHECKSUM}.mp4"
    return StoredVideoClip(
        storage_key=key,
        checksum_sha256=FINAL_CHECKSUM,
        mime_type="video/mp4",
        size_bytes=8192,
        width=1280,
        height=720,
        duration_ms=4000,
        durable_asset_ref=key,
        poster_frame_ref=None,
        tail_frame_ref=None,
        keyframe_refs=(),
    )


async def _prepare() -> None:
    await _cleanup()
    connection = await asyncpg.connect(_migration_dsn())
    try:
        await connection.execute(
            """
            INSERT INTO tasks (
                id, organization_id, project_id, agent_run_id, parent_task_id,
                task_graph_id, recipe_step_id, task_key, type, status,
                owner_agent_key, owner_key, input_json, output_json, metadata_json,
                output_schema, condition_expression, priority, attempt_count,
                max_attempts, budget_reserved, budget_limit_usd, state_version,
                lease_owner, lease_expires_at, heartbeat_at, retry_not_before,
                wait_reason, external_ref, cancellation_requested_at,
                progress_current, progress_total, dynamic_depth, dynamic_child_limit,
                concurrency_group, concurrency_limit, started_at, finished_at,
                created_at, updated_at, version
            ) VALUES (
                $1,$2,$3,NULL,NULL,NULL,NULL,NULL,'video.render','pending',
                NULL,NULL,'{}'::jsonb,'{}'::jsonb,'{}'::jsonb,
                NULL,NULL,100,0,3,0,NULL,1,
                NULL,NULL,NULL,NULL,NULL,NULL,NULL,
                0,1,0,0,NULL,NULL,NULL,NULL,now(),now(),1
            )
            """,
            UUID(TASK),
            UUID(ORG),
            UUID(PROJECT),
        )
    finally:
        await connection.close()


async def _cleanup() -> None:
    connection = await asyncpg.connect(_migration_dsn())
    try:
        async with connection.transaction():
            version_rows = await connection.fetch(
                """
                SELECT av.id
                FROM artifact_versions av
                JOIN artifacts a ON a.id=av.artifact_id
                WHERE a.organization_id=$1
                  AND a.metadata_json ->> 'video_job_id' = $2
                """,
                UUID(ORG),
                VIDEO_JOB_ID,
            )
            version_ids = [row["id"] for row in version_rows]
            if version_ids:
                await connection.execute(
                    """
                    DELETE FROM artifact_edges
                    WHERE organization_id=$1
                      AND (
                        from_artifact_version_id = ANY($2::uuid[])
                        OR to_artifact_version_id = ANY($2::uuid[])
                      )
                    """,
                    UUID(ORG),
                    version_ids,
                )
                await connection.execute(
                    "DELETE FROM artifact_provenance WHERE organization_id=$1 AND artifact_version_id = ANY($2::uuid[])",
                    UUID(ORG),
                    version_ids,
                )
                await connection.execute(
                    "DELETE FROM artifact_files WHERE organization_id=$1 AND artifact_version_id = ANY($2::uuid[])",
                    UUID(ORG),
                    version_ids,
                )
                await connection.execute(
                    """
                    UPDATE artifact_branches ab
                    SET head_version_id=NULL
                    FROM artifacts a
                    WHERE ab.artifact_id=a.id
                      AND a.organization_id=$1
                      AND a.metadata_json ->> 'video_job_id' = $2
                    """,
                    UUID(ORG),
                    VIDEO_JOB_ID,
                )
                await connection.execute(
                    """
                    DELETE FROM artifact_versions av
                    USING artifacts a
                    WHERE av.artifact_id=a.id
                      AND a.organization_id=$1
                      AND a.metadata_json ->> 'video_job_id' = $2
                    """,
                    UUID(ORG),
                    VIDEO_JOB_ID,
                )
            await connection.execute(
                """
                DELETE FROM artifact_branches ab
                USING artifacts a
                WHERE ab.artifact_id=a.id
                  AND a.organization_id=$1
                  AND a.metadata_json ->> 'video_job_id' = $2
                """,
                UUID(ORG),
                VIDEO_JOB_ID,
            )
            await connection.execute(
                """
                DELETE FROM artifacts
                WHERE organization_id=$1
                  AND metadata_json ->> 'video_job_id' = $2
                """,
                UUID(ORG),
                VIDEO_JOB_ID,
            )
            await connection.execute(
                """
                DELETE FROM outbox_events
                WHERE organization_id=$1
                  AND (
                    aggregate_id=$2
                    OR payload_json ->> 'video_job_id' = $3
                  )
                """,
                UUID(ORG),
                UUID(TASK),
                VIDEO_JOB_ID,
            )
            await connection.execute(
                "DELETE FROM cost_ledger WHERE operation_id=$1",
                UUID(IDEMPOTENCY_OPERATION),
            )
            await connection.execute(
                "DELETE FROM idempotency_operations WHERE id=$1",
                UUID(IDEMPOTENCY_OPERATION),
            )
            await connection.execute(
                """
                DELETE FROM video_provider_jobs
                WHERE video_job_id IN (
                    SELECT id FROM video_generation_jobs
                    WHERE organization_id=$1 AND operation_id=$2
                )
                """,
                UUID(ORG),
                UUID(OPERATION),
            )
            await connection.execute(
                "DELETE FROM video_generation_jobs WHERE organization_id=$1 AND operation_id=$2",
                UUID(ORG),
                UUID(OPERATION),
            )
            await connection.execute(
                "DELETE FROM tasks WHERE id=$1 AND organization_id=$2",
                UUID(TASK),
                UUID(ORG),
            )
    finally:
        await connection.close()


@pytest.fixture(autouse=True)
def isolated_video_scope() -> None:
    asyncio.run(_prepare())
    yield
    asyncio.run(_cleanup())


def test_video_repository_round_trip_preserves_external_provider_identity() -> None:
    async def run() -> None:
        spec = _spec()
        job = _job(spec)
        provider_record = _provider_record()
        repository = PostgresVideoRepository(os.environ["DATABASE_URL"])
        repository.save_spec(spec)
        repository.save(job)
        repository.save_provider_job(provider_record)

        assert await repository.flush(organization_id=ORG, operation_id=OPERATION) == job

        reloaded = PostgresVideoRepository(os.environ["DATABASE_URL"])
        assert await reloaded.load(organization_id=ORG, operation_id=OPERATION) == job
        assert reloaded.get_spec(ORG, OPERATION) == spec
        assert (
            reloaded.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION)
            == provider_record
        )

        connection = await asyncpg.connect(_dsn())
        try:
            row = await connection.fetchrow(
                """
                SELECT v.status AS job_status, v.semantic_hash, p.active,
                       p.provider_request_id, p.status AS provider_status
                FROM video_generation_jobs v
                JOIN video_provider_jobs p ON p.video_job_id=v.id
                WHERE v.organization_id=$1 AND v.operation_id=$2
                """,
                UUID(ORG),
                UUID(OPERATION),
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["job_status"] == "WAITING_EXTERNAL"
        assert row["semantic_hash"] == spec.semantic_hash
        assert row["active"] is True
        assert row["provider_request_id"] == PROVIDER_REQUEST_ID
        assert row["provider_status"] == "PENDING"

    asyncio.run(run())


def test_cost_outbox_artifact_and_external_wait_recovery_use_canonical_postgres() -> None:
    async def run() -> None:
        spec = _spec()
        job = _job(spec)
        repository = PostgresVideoRepository(os.environ["DATABASE_URL"])
        repository.save_spec(spec)
        repository.save(job)
        repository.save_provider_job(_provider_record())
        await repository.flush(organization_id=ORG, operation_id=OPERATION)

        migration = await asyncpg.connect(_migration_dsn())
        try:
            await migration.execute(
                """
                INSERT INTO idempotency_operations (
                    id, organization_id, idempotency_key, operation_type,
                    business_scope_id, status, request_hash, lease_owner,
                    lease_expires_at, attempt_count, result_json,
                    created_at, updated_at, version
                ) VALUES (
                    $1,$2,$3,'paid_model_invocation',$4,'succeeded',$5,NULL,
                    NULL,1,'{}'::jsonb,now(),now(),1
                )
                """,
                UUID(IDEMPOTENCY_OPERATION),
                UUID(ORG),
                "video-postgres-paid-op",
                UUID(PAID_OPERATION),
                "f" * 64,
            )
            await migration.execute(
                """
                INSERT INTO cost_ledger (
                    id, organization_id, operation_id, project_id, task_id,
                    provider, model, entry_type, entry_key, amount, currency,
                    pricing_snapshot_id, external_provider_request_id,
                    confidence, cost_basis, source, occurred_at, created_at
                ) VALUES (
                    $1,$2,$3,$4,$5,'openai','sora-2','actual_cost','primary',
                    1.25000000,'USD','sora-price-v1',$6,'exact',
                    'provider_cost','model_gateway',now(),now()
                )
                """,
                uuid4(),
                UUID(ORG),
                UUID(IDEMPOTENCY_OPERATION),
                UUID(PROJECT),
                UUID(TASK),
                PROVIDER_REQUEST_ID,
            )
        finally:
            await migration.close()

        observer = ScopedPostgresVideoCostObserver(os.environ["DATABASE_URL"])
        assert (
            await observer.record_terminal(
                video_job_id=VIDEO_JOB_ID,
                shot_id=SHOT_ID,
                paid_operation_id=PAID_OPERATION,
                provider="openai",
                model="sora-2",
                provider_request_id=PROVIDER_REQUEST_ID,
                amount_usd=Decimal("1.25000000"),
                confidence="EXACT",
                pricing_snapshot_id="sora-price-v1",
            )
            is True
        )

        sink = PostgresVideoEventSink(os.environ["DATABASE_URL"])
        payload = {"status": "WAITING_EXTERNAL", "shot_id": SHOT_ID}
        await sink.emit(
            "video_generation.waiting_external",
            organization_id=ORG,
            video_job_id=VIDEO_JOB_ID,
            payload=payload,
        )
        await sink.emit(
            "video_generation.waiting_external",
            organization_id=ORG,
            video_job_id=VIDEO_JOB_ID,
            payload=payload,
        )

        artifacts = PostgresVideoArtifactAdapter(
            os.environ["DATABASE_URL"],
            bucket="lumi-assets",
        )
        validation = ShotValidationReport(decision="PASS", findings=())
        compiled = _compiled_shot()
        clip_version_id = await artifacts.create_clip(
            spec=spec,
            shot=compiled,
            clip=_clip(),
            provenance=ShotProvenance(
                video_job_id=VIDEO_JOB_ID,
                organization_id=ORG,
                shot_id=SHOT_ID,
                paid_operation_id=PAID_OPERATION,
                storyboard_hash=STORYBOARD_HASH,
                prompt_hash="2" * 64,
                source_refs=(),
                continuity_refs=(),
                provider="openai",
                model="sora-2",
                provider_request_id=PROVIDER_REQUEST_ID,
                routing_reason_codes=("PROFILE_MATCH",),
                pricing_snapshot_id="sora-price-v1",
                cost_usd=Decimal("1.25000000"),
                cost_confidence="exact",
                brand_rule_set_version=None,
                identity_validation_snapshot_id=None,
                code_git_sha=spec.code_git_sha,
            ),
            validation=validation,
            continuity_parent_version_ids=(),
        )
        final_version_id = await artifacts.create_final(
            spec=spec,
            rendered=RenderedVideo(video=_final_clip()),
            provenance=FinalVideoProvenance(
                video_job_id=VIDEO_JOB_ID,
                organization_id=ORG,
                storyboard_hash=STORYBOARD_HASH,
                clip_artifact_version_ids=(clip_version_id,),
                timeline_hash="3" * 64,
                code_git_sha=spec.code_git_sha,
                brand_rule_set_version=None,
            ),
            validation=validation,
            clip_artifact_version_ids=(clip_version_id,),
        )

        message = JobMessage(
            job_id=UUID(TASK),
            organization_id=UUID(ORG),
            project_id=UUID(PROJECT),
            operation_id=UUID(OPERATION),
            trace_id="trace-video-postgres",
        )
        dispatch = JobDispatch(
            task_name=VIDEO_RENDER_TASK_NAME,
            queue=VIDEO_RENDER_QUEUE,
            message=message,
        )
        migration = await asyncpg.connect(_migration_dsn())
        try:
            await migration.execute(
                """
                INSERT INTO outbox_events (
                    id, organization_id, event_name, aggregate_type,
                    aggregate_id, schema_version, payload_json,
                    publish_attempts, created_at
                ) VALUES ($1,$2,$3,'task',$4,$5,$6::jsonb,0,now())
                """,
                uuid4(),
                UUID(ORG),
                JOB_DISPATCH_EVENT_NAME,
                UUID(TASK),
                JOB_DISPATCH_SCHEMA_VERSION,
                json.dumps(dispatch.as_outbox_payload(), separators=(",", ":")),
            )
        finally:
            await migration.close()

        wait = ExternalWait(
            wait_reason="video_provider_pending",
            external_ref="video-provider:postgres-acceptance",
            retry_not_before=datetime.now(UTC) - timedelta(seconds=1),
            output={"video_job_id": VIDEO_JOB_ID},
        )

        async def handler(value: JobMessage) -> ExternalWait:
            assert value == message
            return wait

        store = TaskJobStore(_dsn())
        outcome = await execute_job(store=store, message=message, handler=handler)
        assert outcome.state == JobState.WAITING_EXTERNAL
        assert outcome.attempt_count == 1

        scheduler = MediaExternalWaitWakeScheduler(_dsn())
        wakes = await scheduler.stage_due_batch(limit=10)
        assert len(wakes) == 1
        assert wakes[0].task_id == UUID(TASK)

        resumed_attempt = await store.claim(message)
        assert resumed_attempt == 1

        connection = await asyncpg.connect(_dsn())
        try:
            task_row = await connection.fetchrow(
                """
                SELECT status, attempt_count, wait_reason, retry_not_before
                FROM tasks WHERE id=$1 AND organization_id=$2
                """,
                UUID(TASK),
                UUID(ORG),
            )
            event_rows = await connection.fetch(
                """
                SELECT event_name, payload_json
                FROM outbox_events
                WHERE organization_id=$1
                  AND aggregate_type='video_generation'
                  AND payload_json ->> 'video_job_id' = $2
                """,
                UUID(ORG),
                VIDEO_JOB_ID,
            )
            artifact_row = await connection.fetchrow(
                """
                SELECT a.kind, av.status, af.object_key, af.checksum_sha256,
                       ap.operation
                FROM artifacts a
                JOIN artifact_versions av ON av.artifact_id=a.id
                JOIN artifact_files af ON af.artifact_version_id=av.id
                JOIN artifact_provenance ap ON ap.artifact_version_id=av.id
                WHERE av.id=$1 AND a.organization_id=$2
                """,
                UUID(final_version_id),
                UUID(ORG),
            )
            edge = await connection.fetchrow(
                """
                SELECT edge_type
                FROM artifact_edges
                WHERE organization_id=$1
                  AND from_artifact_version_id=$2
                  AND to_artifact_version_id=$3
                """,
                UUID(ORG),
                UUID(clip_version_id),
                UUID(final_version_id),
            )
            dispatch_count = await connection.fetchval(
                """
                SELECT count(*)
                FROM outbox_events
                WHERE organization_id=$1
                  AND aggregate_type='task'
                  AND aggregate_id=$2
                  AND event_name=$3
                """,
                UUID(ORG),
                UUID(TASK),
                JOB_DISPATCH_EVENT_NAME,
            )
            cost_count = await connection.fetchval(
                "SELECT count(*) FROM cost_ledger WHERE operation_id=$1",
                UUID(IDEMPOTENCY_OPERATION),
            )
        finally:
            await connection.close()

        assert task_row is not None
        assert task_row["status"] == "running"
        assert task_row["attempt_count"] == 1
        assert task_row["wait_reason"] == "video_provider_pending"
        assert task_row["retry_not_before"] is None

        assert len(event_rows) == 1
        assert event_rows[0]["event_name"] == "video_generation.waiting_external"
        assert event_rows[0]["payload_json"]["shot_id"] == SHOT_ID

        assert artifact_row is not None
        assert artifact_row["kind"] == "VIDEO"
        assert artifact_row["status"] == "ready"
        assert artifact_row["object_key"].startswith(
            f"generated/video/v1/{ORG}/{PROJECT}/final/"
        )
        assert artifact_row["checksum_sha256"] == FINAL_CHECKSUM
        assert artifact_row["operation"] == "video.generate.final"
        assert edge is not None
        assert edge["edge_type"] == "COMPOSED_FROM"
        assert dispatch_count == 2
        assert cost_count == 1

    asyncio.run(run())

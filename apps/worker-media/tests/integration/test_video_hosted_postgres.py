from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
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

ORG = UUID("01900000-0000-7000-8000-000000000001")
PROJECT = UUID("01900000-0000-7000-8000-000000000006")
SHOT_ID = "hero"
STORYBOARD_HASH = "b" * 64
REQUEST_HASH = "c" * 64
CLIP_CHECKSUM = "d" * 64
FINAL_CHECKSUM = "e" * 64


@dataclass(frozen=True, slots=True)
class _Scope:
    task_id: UUID
    operation_id: UUID
    paid_operation_id: UUID
    idempotency_operation_id: UUID
    video_job_id: str
    provider_request_id: str


def _scope() -> _Scope:
    paid = uuid4()
    return _Scope(
        task_id=uuid4(),
        operation_id=uuid4(),
        paid_operation_id=paid,
        idempotency_operation_id=uuid4(),
        video_job_id=f"video-job:{uuid4().hex}",
        provider_request_id=f"video_pg_{paid.hex}",
    )


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _migration_dsn() -> str:
    return os.environ.get("MIGRATION_DATABASE_URL", os.environ["DATABASE_URL"]).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


async def _insert_task(scope: _Scope) -> None:
    """Create only mutable task state; later Alembic columns use their DB defaults."""
    connection = await asyncpg.connect(_migration_dsn())
    try:
        await connection.execute(
            """
            INSERT INTO tasks (
                id, organization_id, project_id, type, status,
                input_json, output_json, priority, attempt_count, max_attempts,
                budget_reserved, created_at, updated_at, version
            ) VALUES (
                $1,$2,$3,'video.render','pending',
                '{}'::jsonb,'{}'::jsonb,100,0,3,0,now(),now(),1
            )
            """,
            scope.task_id,
            ORG,
            PROJECT,
        )
    finally:
        await connection.close()


def _spec(scope: _Scope) -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=str(ORG),
        project_id=str(PROJECT),
        task_id=str(scope.task_id),
        operation_id=str(scope.operation_id),
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


def _job(scope: _Scope, spec: VideoTaskSpec) -> VideoJob:
    return VideoJob(
        video_job_id=scope.video_job_id,
        organization_id=str(ORG),
        operation_id=str(scope.operation_id),
        semantic_hash=spec.semantic_hash,
        storyboard_hash=STORYBOARD_HASH,
        status="WAITING_EXTERNAL",
        shots=(
            ShotRuntime(
                shot_id=SHOT_ID,
                ordinal=1,
                paid_operation_id=str(scope.paid_operation_id),
                status="WAITING_EXTERNAL",
                attempt_count=1,
                provider="openai",
                model="sora-2",
                provider_request_id=scope.provider_request_id,
            ),
        ),
        estimated_cost_usd=Decimal("1.25000000"),
    )


def _provider_record(scope: _Scope) -> ProviderJobRecord:
    return ProviderJobRecord(
        organization_id=str(ORG),
        video_job_id=scope.video_job_id,
        shot_id=SHOT_ID,
        paid_operation_id=str(scope.paid_operation_id),
        request_hash=REQUEST_HASH,
        result=GatewayVideoResult(
            status="PENDING",
            provider="openai",
            model="sora-2",
            provider_request_id=scope.provider_request_id,
            output_ref=None,
            output_mime_type=None,
            cost_usd=Decimal("1.25000000"),
            cost_confidence="estimated",
            pricing_snapshot_id="sora-price-v1",
            routing_reason_codes=("PROFILE_MATCH",),
        ),
    )


def _compiled_shot(scope: _Scope, spec: VideoTaskSpec) -> CompiledShot:
    return CompiledShot(
        shot=spec.shots[0],
        paid_operation_id=str(scope.paid_operation_id),
        ordinal=1,
    )


def _clip(scope: _Scope) -> StoredVideoClip:
    key = (
        f"generated/video/v1/{ORG}/{PROJECT}/shots/"
        f"{scope.paid_operation_id.hex}/{CLIP_CHECKSUM}.mp4"
    )
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


def _final_clip(scope: _Scope) -> StoredVideoClip:
    key = (
        f"generated/video/v1/{ORG}/{PROJECT}/final/"
        f"{scope.operation_id.hex}/{FINAL_CHECKSUM}.mp4"
    )
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


async def _persist_waiting_job(
    scope: _Scope,
) -> tuple[VideoTaskSpec, VideoJob, ProviderJobRecord]:
    await _insert_task(scope)
    spec = _spec(scope)
    job = _job(scope, spec)
    provider = _provider_record(scope)
    repository = PostgresVideoRepository(os.environ["DATABASE_URL"])
    repository.save_spec(spec)
    repository.save(job)
    repository.save_provider_job(provider)
    assert (
        await repository.flush(
            organization_id=str(ORG),
            operation_id=str(scope.operation_id),
        )
        == job
    )
    return spec, job, provider


def test_video_repository_round_trip_preserves_external_provider_identity() -> None:
    async def run() -> None:
        scope = _scope()
        spec, job, provider = await _persist_waiting_job(scope)

        reloaded = PostgresVideoRepository(os.environ["DATABASE_URL"])
        assert (
            await reloaded.load(
                organization_id=str(ORG),
                operation_id=str(scope.operation_id),
            )
            == job
        )
        assert reloaded.get_spec(str(ORG), str(scope.operation_id)) == spec
        assert (
            reloaded.get_provider_job(
                str(ORG),
                scope.video_job_id,
                SHOT_ID,
                str(scope.paid_operation_id),
            )
            == provider
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
                ORG,
                scope.operation_id,
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["job_status"] == "WAITING_EXTERNAL"
        assert row["semantic_hash"] == spec.semantic_hash
        assert row["active"] is True
        assert row["provider_request_id"] == scope.provider_request_id
        assert row["provider_status"] == "PENDING"

    asyncio.run(run())


def test_cost_outbox_artifact_and_external_wait_recovery_use_canonical_postgres() -> None:
    async def run() -> None:
        scope = _scope()
        spec, _, _ = await _persist_waiting_job(scope)

        # Cost truth and Artifact history are intentionally append-only. The test uses
        # unique identities and lets the workflow's final infra-reset destroy this
        # ephemeral PostgreSQL database instead of bypassing immutable triggers.
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
                scope.idempotency_operation_id,
                ORG,
                f"video-postgres-paid-op:{scope.paid_operation_id}",
                scope.paid_operation_id,
                "f" * 64,
            )
            await migration.execute(
                """
                INSERT INTO cost_ledger (
                    id, organization_id, operation_id,
                    provider, model, entry_type, entry_key, amount, currency,
                    pricing_snapshot_id, external_provider_request_id,
                    confidence, cost_basis, source, occurred_at, created_at
                ) VALUES (
                    $1,$2,$3,'openai','sora-2','actual_cost','primary',
                    1.25000000,'USD','sora-price-v1',$4,'exact',
                    'provider_cost','model_gateway',now(),now()
                )
                """,
                uuid4(),
                ORG,
                scope.idempotency_operation_id,
                scope.provider_request_id,
            )
        finally:
            await migration.close()

        observer = ScopedPostgresVideoCostObserver(os.environ["DATABASE_URL"])
        assert (
            await observer.record_terminal(
                video_job_id=scope.video_job_id,
                shot_id=SHOT_ID,
                paid_operation_id=str(scope.paid_operation_id),
                provider="openai",
                model="sora-2",
                provider_request_id=scope.provider_request_id,
                amount_usd=Decimal("1.25000000"),
                confidence="EXACT",
                pricing_snapshot_id="sora-price-v1",
            )
            is True
        )

        sink = PostgresVideoEventSink(os.environ["DATABASE_URL"])
        payload = {"status": "WAITING_EXTERNAL", "shot_id": SHOT_ID}
        for _ in range(2):
            await sink.emit(
                "video_generation.waiting_external",
                organization_id=str(ORG),
                video_job_id=scope.video_job_id,
                payload=payload,
            )

        artifacts = PostgresVideoArtifactAdapter(
            os.environ["DATABASE_URL"],
            bucket="lumi-assets",
        )
        validation = ShotValidationReport(decision="PASS", findings=())
        clip_version_id = await artifacts.create_clip(
            spec=spec,
            shot=_compiled_shot(scope, spec),
            clip=_clip(scope),
            provenance=ShotProvenance(
                video_job_id=scope.video_job_id,
                organization_id=str(ORG),
                shot_id=SHOT_ID,
                paid_operation_id=str(scope.paid_operation_id),
                storyboard_hash=STORYBOARD_HASH,
                prompt_hash="2" * 64,
                source_refs=(),
                continuity_refs=(),
                provider="openai",
                model="sora-2",
                provider_request_id=scope.provider_request_id,
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
            rendered=RenderedVideo(video=_final_clip(scope)),
            provenance=FinalVideoProvenance(
                video_job_id=scope.video_job_id,
                organization_id=str(ORG),
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
            job_id=scope.task_id,
            organization_id=ORG,
            project_id=PROJECT,
            operation_id=scope.operation_id,
            trace_id=f"trace-video-postgres-{scope.operation_id.hex}",
        )
        dispatch = JobDispatch(
            task_name=VIDEO_RENDER_TASK_NAME,
            queue=VIDEO_RENDER_QUEUE,
            message=message,
        )
        connection = await asyncpg.connect(_dsn())
        try:
            await connection.execute(
                """
                INSERT INTO outbox_events (
                    id, organization_id, event_name, aggregate_type,
                    aggregate_id, schema_version, payload_json,
                    publish_attempts, created_at
                ) VALUES ($1,$2,$3,'task',$4,$5,$6::jsonb,0,now())
                """,
                uuid4(),
                ORG,
                JOB_DISPATCH_EVENT_NAME,
                scope.task_id,
                JOB_DISPATCH_SCHEMA_VERSION,
                json.dumps(dispatch.as_outbox_payload(), separators=(",", ":")),
            )
        finally:
            await connection.close()

        wait = ExternalWait(
            wait_reason="video_provider_pending",
            external_ref=f"video-provider:{scope.provider_request_id}",
            retry_not_before=datetime.now(UTC) - timedelta(seconds=1),
            output={"video_job_id": scope.video_job_id},
        )

        async def handler(value: JobMessage) -> ExternalWait:
            assert value == message
            return wait

        store = TaskJobStore(_dsn())
        outcome = await execute_job(store=store, message=message, handler=handler)
        assert outcome.state == JobState.WAITING_EXTERNAL
        assert outcome.attempt_count == 1

        wakes = await MediaExternalWaitWakeScheduler(_dsn()).stage_due_batch(limit=10)
        matching = [item for item in wakes if item.task_id == scope.task_id]
        assert len(matching) == 1

        resumed_attempt = await store.claim(message)
        assert resumed_attempt == 1

        connection = await asyncpg.connect(_dsn())
        try:
            task_row = await connection.fetchrow(
                """
                SELECT status, attempt_count, retry_not_before
                FROM tasks WHERE id=$1 AND organization_id=$2
                """,
                scope.task_id,
                ORG,
            )
            event_rows = await connection.fetch(
                """
                SELECT event_name, payload_json
                FROM outbox_events
                WHERE organization_id=$1
                  AND aggregate_type='video_generation'
                  AND payload_json ->> 'video_job_id' = $2
                """,
                ORG,
                scope.video_job_id,
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
                ORG,
            )
            edge = await connection.fetchrow(
                """
                SELECT edge_type
                FROM artifact_edges
                WHERE organization_id=$1
                  AND from_artifact_version_id=$2
                  AND to_artifact_version_id=$3
                """,
                ORG,
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
                ORG,
                scope.task_id,
                JOB_DISPATCH_EVENT_NAME,
            )
            cost_count = await connection.fetchval(
                "SELECT count(*) FROM cost_ledger WHERE operation_id=$1",
                scope.idempotency_operation_id,
            )
        finally:
            await connection.close()

        assert task_row is not None
        assert task_row["status"] == "running"
        assert task_row["attempt_count"] == 1
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

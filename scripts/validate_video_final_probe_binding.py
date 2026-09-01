#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL_PROBE = ROOT / "apps/worker-media/src/lumi_worker_media/video_final_probe_runtime.py"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
HOSTED_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
EVENT_BUFFER = ROOT / "apps/worker-media/src/lumi_worker_media/video_event_buffer.py"
OUTPUT_RECOVERY = ROOT / "apps/worker-media/src/lumi_worker_media/video_output_recovery.py"
HOSTED_VALIDATION = ROOT / "apps/worker-media/src/lumi_worker_media/video_validation_runtime.py"
FINAL_PROBE_TEST = ROOT / "apps/worker-media/tests/test_video_final_probe_runtime.py"
EVENT_UOW_TEST = ROOT / "apps/worker-media/tests/test_video_event_uow.py"
OUTPUT_RECOVERY_TEST = ROOT / "apps/worker-media/tests/test_video_output_recovery.py"
HOSTED_VALIDATION_TEST = ROOT / "apps/worker-media/tests/test_video_validation_runtime.py"
SANDBOX_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py"
STORAGE_IAC = ROOT / "infra/iac/modules/storage/main.tf"
MODEL_GATEWAY_VIDEO_ADAPTER = (
    ROOT / "services/model-gateway/src/lumi_model_gateway/openai_video_adapter.py"
)
MODEL_GATEWAY_VIDEO_TEST = ROOT / "services/model-gateway/tests/test_openai_video_adapter.py"
RUNTIME_IMAGE_MANIFEST = ROOT / "production/runtime-images/manifest-v1.json"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
SELF_PATH = "scripts/validate_video_final_probe_binding.py"
FINAL_PROBE_PATH = "apps/worker-media/src/lumi_worker_media/video_final_probe_runtime.py"
HOSTED_VALIDATION_PATH = "apps/worker-media/src/lumi_worker_media/video_validation_runtime.py"
EVENT_BUFFER_PATH = "apps/worker-media/src/lumi_worker_media/video_event_buffer.py"
OUTPUT_RECOVERY_PATH = "apps/worker-media/src/lumi_worker_media/video_output_recovery.py"
MODEL_GATEWAY_VIDEO_ADAPTER_PATH = (
    "services/model-gateway/src/lumi_model_gateway/openai_video_adapter.py"
)


class VideoFinalProbeContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VideoFinalProbeContractError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def require_python_syntax(source: str, path: Path) -> None:
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        raise VideoFinalProbeContractError(
            f"{path.relative_to(ROOT)} has invalid Python syntax: {exc}"
        ) from exc


def main() -> int:
    final_probe = read(FINAL_PROBE)
    hosted = read(HOSTED_RUNTIME)
    repository = read(HOSTED_REPOSITORY)
    event_buffer = read(EVENT_BUFFER)
    output_recovery = read(OUTPUT_RECOVERY)
    hosted_validation = read(HOSTED_VALIDATION)
    tests = read(FINAL_PROBE_TEST)
    event_uow_tests = read(EVENT_UOW_TEST)
    output_recovery_tests = read(OUTPUT_RECOVERY_TEST)
    hosted_validation_tests = read(HOSTED_VALIDATION_TEST)
    sandbox = read(SANDBOX_RUNTIME)
    storage_iac = read(STORAGE_IAC)
    model_gateway_video_adapter = read(MODEL_GATEWAY_VIDEO_ADAPTER)
    model_gateway_video_test = read(MODEL_GATEWAY_VIDEO_TEST)
    workflow = read(VIDEO_WORKFLOW)
    final = read(FINAL_WORKFLOW)

    for source, path in (
        (model_gateway_video_adapter, MODEL_GATEWAY_VIDEO_ADAPTER),
        (model_gateway_video_test, MODEL_GATEWAY_VIDEO_TEST),
        (hosted, HOSTED_RUNTIME),
        (repository, HOSTED_REPOSITORY),
        (event_buffer, EVENT_BUFFER),
        (event_uow_tests, EVENT_UOW_TEST),
        (output_recovery, OUTPUT_RECOVERY),
        (output_recovery_tests, OUTPUT_RECOVERY_TEST),
    ):
        require_python_syntax(source, path)

    require_markers(
        final_probe,
        (
            "class HostedVerifiedVideoMediaSandbox",
            "await self.renderer.render(timeline)",
            "await self._probe_durable(rendered)",
            "generated/video/v1/",
            "sandbox-exchange/v1/",
            '"ffprobe"',
            '"/sandbox/input/final.mp4"',
            "_decode_ffprobe(stdout)",
            "VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH",
            "VIDEO_FINAL_PROBE_STAGE_IDENTITY_MISMATCH",
            "VIDEO_FINAL_CONTAINER_UNSUPPORTED",
            "VIDEO_FINAL_CODEC_MISMATCH",
            "VIDEO_FINAL_RESOLUTION_MISMATCH",
            "VIDEO_FINAL_FPS_MISMATCH",
            "VIDEO_FINAL_DURATION_MISMATCH",
            "VIDEO_FINAL_UNEXPECTED_AUDIO",
            "verified_video = replace(",
            "rendered.video,",
            "duration_ms=int(probe.duration_seconds * Decimal(\"1000\"))",
        ),
        "Hosted final durable probe",
    )
    require(
        final_probe.find("await self._probe_durable(rendered)")
        < final_probe.find("return _verified_final_render(rendered, timeline, probe)"),
        "final durable ffprobe must precede verified metadata return",
    )

    # OpenAI Videos currently exposes final size and duration controls but no FPS
    # create field. Keep the internal final-output FPS intent provider-neutral and do
    # not fabricate a native provider field that the adapter cannot guarantee.
    require_markers(
        model_gateway_video_adapter,
        (
            "class OpenAIVideoGenerationAdapter",
            '"model": self._descriptor.model',
            '"prompt": self._prompt(request)',
            '"seconds": str(seconds)',
            '"size": size',
            "_OPENAI_VIDEOS_URL",
        ),
        "OpenAI hosted video adapter",
    )
    invoke_start = model_gateway_video_adapter.find("    async def invoke(")
    status_start = model_gateway_video_adapter.find(
        "    async def get_async_status(", invoke_start
    )
    require(
        invoke_start >= 0 and status_start > invoke_start,
        "OpenAI hosted video adapter invoke boundary is missing",
    )
    invoke_block = model_gateway_video_adapter[invoke_start:status_start]
    require(
        '"fps"' not in invoke_block,
        "OpenAI native /v1/videos create payload must not fabricate an unsupported FPS field",
    )
    require_markers(
        model_gateway_video_test,
        (
            '"fps": 24',
            'assert request.constraints["fps"] == 24',
            '"https://api.openai.com/v1/videos"',
            'assert "fps" not in transport.calls[0][2]',
            '"model": "sora-2"',
            '"seconds": "4"',
            '"size": "1280x720"',
        ),
        "OpenAI hosted video FPS ownership test",
    )

    # Raw provider FPS is not a controllable OpenAI Videos create parameter. Hosted
    # raw validation must not turn it into a post-payment rejection condition; the
    # final typed ffmpeg render and durable ffprobe own output FPS correctness.
    require_markers(
        hosted_validation,
        (
            "class HostedV1VideoValidator",
            "does not expose an FPS control",
            "Raw-shot acceptance remains fail-closed",
            "VIDEO_DECODE_FAILED",
            "VIDEO_MIME_MISMATCH",
            "VIDEO_RESOLUTION_MISMATCH",
            "VIDEO_DURATION_MISMATCH",
            "VIDEO_PROVIDER_SAFETY_BLOCK",
            'decision="REJECT" if frozen else "PASS"',
        ),
        "Hosted raw video validation",
    )
    require(
        "VIDEO_FPS_MISMATCH" not in hosted_validation,
        "Hosted raw provider validation must not reject an uncontrollable provider FPS",
    )
    require_markers(
        hosted,
        (
            "HostedV1VideoValidator",
            "validator=HostedV1VideoValidator()",
        ),
        "Hosted raw validator composition",
    )
    require_markers(
        hosted_validation_tests,
        (
            "test_hosted_raw_provider_fps_is_not_mistaken_for_final_output_fps",
            'fps=Decimal("30")',
            "assert spec.fps == 24",
            'assert report.decision == "PASS"',
            "test_hosted_raw_resolution_mismatch_still_rejects",
            "VIDEO_RESOLUTION_MISMATCH",
            "test_hosted_raw_duration_mismatch_still_rejects",
            "VIDEO_DURATION_MISMATCH",
            "test_hosted_raw_provider_safety_block_still_rejects",
            "VIDEO_PROVIDER_SAFETY_BLOCK",
        ),
        "Hosted raw video validation tests",
    )

    # The lower-level bridge is allowed to carry expected timeline metadata only as
    # an intermediate transport object. The Hosted composition must never feed that
    # object directly into NODE-48 final validation.
    require_markers(
        sandbox,
        (
            "duration_ms = int(duration_seconds * Decimal(\"1000\"))",
            "width=timeline.output_spec.width",
            "height=timeline.output_spec.height",
        ),
        "Sandbox intermediate expected metadata",
    )
    require_markers(
        hosted,
        (
            "HostedVerifiedVideoMediaSandbox",
            "base_sandbox = HostedVideoMediaSandbox.from_spec(spec)",
            "sandbox = HostedVerifiedVideoMediaSandbox(",
            "renderer=base_sandbox",
            "probe_adapter=output",
            "sandbox=TimedMediaSandbox(",
        ),
        "Hosted video final-probe composition",
    )
    require(
        hosted.find("sandbox = HostedVerifiedVideoMediaSandbox(")
        < hosted.find("sandbox=TimedMediaSandbox("),
        "TimedMediaSandbox must wrap the verified final-probe sandbox",
    )

    require_markers(
        tests,
        (
            "test_final_render_is_reprobed_and_expected_metadata_is_not_trusted",
            "assert rendered.video.width == 1",
            "assert verified.video.width == 1280",
            "assert verified.video.duration_ms == 4000",
            "test_final_render_fps_mismatch_fails_before_artifact",
            "VIDEO_FINAL_FPS_MISMATCH",
            "test_final_render_unexpected_audio_fails_before_artifact",
            "VIDEO_FINAL_UNEXPECTED_AUDIO",
            "test_final_render_durable_checksum_mismatch_fails_before_ffprobe",
            "VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH",
            "assert called is False",
        ),
        "Hosted final durable probe tests",
    )

    # Hosted Video domain events must commit with the recovery/provider/public
    # Generation snapshot. The pipeline emits only into an invocation-local buffer;
    # the repository flushes that buffer on its existing PostgreSQL transaction and
    # clears it only after the transaction context has committed successfully.
    require_markers(
        event_buffer,
        (
            "class BufferedVideoEventSink",
            "self._pending: dict[UUID, BufferedVideoEvent] = {}",
            "async def flush_into(self, connection: asyncpg.Connection)",
            "INSERT INTO outbox_events",
            "ON CONFLICT (id) DO NOTHING",
            "def mark_committed(self) -> None:",
            "self._pending.clear()",
        ),
        "Hosted video buffered event UoW",
    )
    require_markers(
        hosted,
        (
            "from .video_event_buffer import BufferedVideoEventSink",
            "events = BufferedVideoEventSink(self.database_dsn)",
            "events=events",
            "event_sink=events",
        ),
        "Hosted video buffered-event composition",
    )
    require(
        "PostgresVideoEventSink(" not in hosted,
        "Hosted runtime must not reintroduce an immediate independent event transaction",
    )
    require_markers(
        repository,
        (
            "event_sink: BufferedVideoEventSink | None = None",
            'raise RuntimeError("VIDEO_EVENT_UOW_DATABASE_MISMATCH")',
            "async with connection.transaction():",
            "await _sync_public_generation(connection, spec=spec, job=job)",
            "await event_sink.flush_into(connection)",
            "event_sink.mark_committed()",
        ),
        "Hosted video atomic repository/event flush",
    )
    flush_start = repository.find("    async def flush(")
    connect_at = repository.find("        connection = await asyncpg.connect(self.dsn)", flush_start)
    mismatch_at = repository.find("VIDEO_EVENT_UOW_DATABASE_MISMATCH", flush_start)
    transaction_at = repository.find("            async with connection.transaction():", flush_start)
    event_flush_at = repository.find("                    await event_sink.flush_into(connection)", flush_start)
    event_commit_at = repository.find("                event_sink.mark_committed()", flush_start)
    require(
        flush_start >= 0
        and mismatch_at > flush_start
        and connect_at > mismatch_at,
        "event UoW database identity must fail closed before PostgreSQL connection",
    )
    require(
        transaction_at > connect_at
        and event_flush_at > transaction_at
        and event_commit_at > event_flush_at,
        "buffered events must stage inside the repository transaction and clear only after commit",
    )
    require_markers(
        event_uow_tests,
        (
            "test_buffered_video_event_is_idempotent_until_transaction_commit",
            "assert sink.pending_count == 1",
            "sink.mark_committed()",
            "assert sink.pending_count == 0",
            "test_buffered_video_event_remains_pending_when_transaction_write_fails",
            "test_video_repository_rejects_event_uow_database_mismatch_before_connect",
            "VIDEO_EVENT_UOW_DATABASE_MISMATCH",
        ),
        "Hosted video event UoW executable tests",
    )

    # Provider-output deletion must happen only after the recovery/event transaction
    # commits. The underlying adapter may call delete_candidate in a finally block,
    # so Hosted composition replaces its object store with a deferred-delete wrapper.
    require_markers(
        output_recovery,
        (
            "class DeferredProviderOutputStore",
            '_PROVIDER_OUTPUT_PREFIX = "provider-output/v1/async/"',
            "self._pending_provider_deletes.add((bucket, object_key))",
            "await self.delegate.delete_candidate(bucket=bucket, object_key=object_key)",
            "async def cleanup_committed_provider_outputs",
            "except Exception:",
            "self._pending_provider_deletes.discard((bucket, object_key))",
        ),
        "Hosted video provider-output recovery wrapper",
    )
    require_markers(
        hosted,
        (
            "from .video_output_recovery import DeferredProviderOutputStore",
            "output_recovery = DeferredProviderOutputStore(output.object_store)",
            "output.object_store = cast(S3ObjectStore, output_recovery)",
            "await output_recovery.cleanup_committed_provider_outputs()",
        ),
        "Hosted video deferred provider-output cleanup composition",
    )
    snapshot_flush_at = hosted.find("        persisted = await repository.flush(")
    snapshot_match_at = hosted.find("        if persisted != job:", snapshot_flush_at)
    output_cleanup_at = hosted.find(
        "        await output_recovery.cleanup_committed_provider_outputs()",
        snapshot_flush_at,
    )
    require(
        snapshot_flush_at >= 0
        and snapshot_match_at > snapshot_flush_at
        and output_cleanup_at > snapshot_match_at,
        "provider-output cleanup must occur only after committed snapshot identity verification",
    )
    require_markers(
        output_recovery_tests,
        (
            "test_provider_output_delete_is_deferred_but_exchange_cleanup_is_immediate",
            "assert store.pending_provider_delete_count == 1",
            "cleanup_committed_provider_outputs",
            "test_provider_cleanup_failure_is_nonfatal_and_left_for_lifecycle_fallback",
            "test_non_provider_delete_failure_remains_fail_closed",
        ),
        "Hosted video provider-output recovery tests",
    )
    require_markers(
        storage_iac,
        (
            'for_each = each.key == "assets" ? [1] : []',
            'id     = "expire-provider-output-staging"',
            'prefix = "provider-output/v1/async/"',
            "days = 1",
            "noncurrent_days = 1",
        ),
        "provider-output lifecycle fallback",
    )

    try:
        runtime_manifest = json.loads(
            RUNTIME_IMAGE_MANIFEST.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoFinalProbeContractError("runtime image manifest is unreadable") from exc
    runtimes = runtime_manifest.get("runtimes")
    worker = runtimes.get("worker-media") if isinstance(runtimes, dict) else None
    worker_sources = worker.get("source_paths") if isinstance(worker, dict) else None
    require(
        isinstance(worker_sources, list)
        and FINAL_PROBE_PATH in worker_sources
        and HOSTED_VALIDATION_PATH in worker_sources
        and EVENT_BUFFER_PATH in worker_sources
        and OUTPUT_RECOVERY_PATH in worker_sources,
        "canonical worker-media provenance omits final/raw/event/output-recovery video sources",
    )
    model_gateway = runtimes.get("model-gateway") if isinstance(runtimes, dict) else None
    model_gateway_sources = (
        model_gateway.get("source_paths") if isinstance(model_gateway, dict) else None
    )
    require(
        isinstance(model_gateway_sources, list)
        and MODEL_GATEWAY_VIDEO_ADAPTER_PATH in model_gateway_sources,
        "canonical model-gateway image provenance does not bind OpenAI hosted video adapter",
    )

    for source, label in (
        (workflow, "Video Generation workflow"),
        (final, "Final Acceptance workflow"),
    ):
        require(
            f"python3 {SELF_PATH}" in source,
            f"{label} does not execute final durable probe/event/recovery contract",
        )
        require(
            f"{SELF_PATH} \\" in source,
            f"{label} does not syntax-gate final durable probe/event/recovery contract",
        )
    require(
        'apps/worker-media/src/lumi_worker_media/video_*.py' in workflow,
        "Video Generation workflow does not syntax-gate hosted video runtime sources",
    )
    require(
        'apps/worker-media/tests/test_video_*.py' in workflow,
        "Video Generation workflow does not execute Hosted video recovery regressions",
    )
    require(
        f"{FINAL_PROBE_PATH} \\" in final
        and f"{HOSTED_VALIDATION_PATH} \\" in final,
        "Final Acceptance does not directly syntax-gate hosted video validation boundaries",
    )

    print("Hosted video provider/raw/final/event/output-recovery contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VideoFinalProbeContractError as exc:
        raise SystemExit(f"Hosted video final durable probe contract failed: {exc}") from exc

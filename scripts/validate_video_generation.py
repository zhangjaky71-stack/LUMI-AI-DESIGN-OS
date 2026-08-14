from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from lumi_video_generation.model import VideoMode

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/video-generation/node-48-conformance.json"
PIPELINE = ROOT / "services/video-generation/src/lumi_video_generation/pipeline.py"
MODEL = ROOT / "services/video-generation/src/lumi_video_generation/model.py"
GATEWAY = ROOT / "services/video-generation/src/lumi_video_generation/model_gateway_adapter.py"
ROUTER = ROOT / "services/model-gateway/src/lumi_model_gateway/routing.py"
SANDBOX = ROOT / "services/video-generation/src/lumi_video_generation/media_sandbox.py"
OUTPUT = ROOT / "services/video-generation/src/lumi_video_generation/output_adapter.py"
ARTIFACT = ROOT / "services/video-generation/src/lumi_video_generation/artifact_adapter.py"
REPOSITORY = ROOT / "services/video-generation/src/lumi_video_generation/repository.py"
MIGRATION = ROOT / "db/migrations/0007_video_generation.sql"
TESTS = ROOT / "services/video-generation/tests/test_video_generation.py"
OUTPUT_TESTS = ROOT / "services/video-generation/tests/test_video_output_adapter.py"
ROUTING_TESTS = ROOT / "services/video-generation/tests/test_video_routing_and_sandbox.py"
PROVIDER_REPORT = ROOT / "reports/nodes/NODE-48/provider-benchmark.md"

EXPECTED_MODES = {"TEXT_TO_VIDEO", "IMAGE_TO_VIDEO", "STORYBOARD_MULTI_SHOT"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    require(set(get_args(VideoMode)) == EXPECTED_MODES, "VideoMode contract drift")
    require(set(fixture["modes"]) == EXPECTED_MODES, "fixture mode drift")
    require(int(fixture["synthetic_case_count"]) >= 40, "synthetic conformance matrix too small")
    require(sum(int(item["count"]) for item in fixture["case_matrix"]) == int(fixture["synthetic_case_count"]), "fixture count mismatch")

    pipeline = PIPELINE.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")
    gateway = GATEWAY.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    sandbox = SANDBOX.read_text(encoding="utf-8")
    output = OUTPUT.read_text(encoding="utf-8")
    artifact = ARTIFACT.read_text(encoding="utf-8")
    repository = REPOSITORY.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    output_tests = OUTPUT_TESTS.read_text(encoding="utf-8")
    routing_tests = ROUTING_TESTS.read_text(encoding="utf-8")
    sql = MIGRATION.read_text(encoding="utf-8")
    provider_report = PROVIDER_REPORT.read_text(encoding="utf-8")

    require("WAITING_EXTERNAL" in model and "resume(" in pipeline, "long-running external wait state missing")
    require("await self.gateway.poll" in pipeline, "provider resume poll missing")
    require("asyncio.sleep" not in pipeline and "time.sleep" not in pipeline, "pipeline must never hold worker by sleeping")
    require("quality_retry_limit" in model and "retry_shot_operation_id" in pipeline, "quality retry contract missing")
    require("excluded_provider_keys" in pipeline and "excluded_provider_keys" in gateway, "alternate-provider retry exclusion missing")
    require("allowed_provider_keys" in gateway and "VideoFeatureRegistry" in gateway, "provider feature allowlist missing")
    require("allowed_provider_keys" in router and "excluded_provider_keys" in router, "Model Gateway request provider-key gates missing")
    require("terminal_provider_jobs" in repository and "paid_operation_id" in repository, "terminal attempt recovery missing")

    forbidden = ("shell=True", "os.system(", "subprocess.run(", "Popen(")
    for token in forbidden:
        require(token not in sandbox, f"unsafe media execution primitive found: {token}")
    require("FfmpegInvocation" in sandbox and "argv: tuple[str, ...]" in sandbox, "typed ffmpeg argv contract missing")
    require("SandboxExecutor" in sandbox and "network_disabled: bool = True" in sandbox, "sandbox executor/limits missing")
    require("adelay=" in sandbox and "amix=inputs=" in sandbox, "typed multi-track audio mixing missing")
    require("VIDEO_FFMPEG_TRANSITION_NOT_SUPPORTED_V1" in sandbox, "unsupported transition must fail closed")

    require("fetch_to_staging" in output and "discard_staging" in output, "provider output staging boundary missing")
    require("VIDEO_DURABLE_CHECKSUM_MISMATCH" in output, "durable video checksum verification missing")
    require("source_ref=output_ref" in output, "provider output ref must terminate at staging fetch")
    require('type="VIDEO"' in artifact and 'type="COMPOSED_FROM"' in artifact, "video Artifact lineage missing")
    require("provenance.paid_operation_id" in artifact, "shot attempt artifact identity must bind paid operation")
    require("Decimal" in model and "float" in model, "Decimal validation contract missing")

    required_sql = (
        "video_generation_jobs",
        "video_generation_shots",
        "video_provider_jobs",
        "video_generation_cost_reconciliation",
        "video_timelines",
        "video_generation_provenance",
        "video_validation_findings",
        "numeric(20,8)",
        "current_paid_operation_id uuid NOT NULL",
        "paid_operation_id uuid NOT NULL",
        "WHERE active",
        "Provider completion rows are retained",
    )
    for token in required_sql:
        require(token in sql, f"missing SQL contract: {token}")
    require("double precision" not in sql.casefold(), "video financial/schema values must not use double precision")
    require(" real " not in sql.casefold(), "video financial/schema values must not use real float")

    test_tokens = (
        "test_async_single_shot_does_not_poll_inside_start",
        "test_two_shot_storyboard_creates_clip_lineage",
        "test_quality_retry_uses_new_paid_operation",
        "test_real_model_gateway_video_async_submit_poll_poll",
        "test_image_to_video_requires_feature_registry",
        "test_ffmpeg_compiler_uses_argv_not_shell",
    )
    for token in test_tokens:
        require(token in tests, f"missing executable evidence: {token}")
    require("test_provider_url_stops_at_staging" in output_tests, "staged output regression missing")
    require("test_request_provider_exclusion_routes_retry_to_second_provider" in routing_tests, "provider retry exclusion regression missing")
    require("test_multi_track_audio_is_compiled" in routing_tests, "multi-track audio regression missing")

    require("PENDING" in provider_report and "no live provider score" in provider_report.casefold(), "live provider benchmark honesty gate missing")
    print("NODE-48 video generation architecture contract: OK")


if __name__ == "__main__":
    main()

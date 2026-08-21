#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCT_APP = ROOT / "apps/api/src/lumi_api/product_app.py"
API_ROUTER = ROOT / "apps/api/src/lumi_api/api/v1/router.py"
GENERATION_GATEWAY = ROOT / "apps/api/src/lumi_api/generations/gateway.py"
GENERATION_SERVICE = ROOT / "apps/api/src/lumi_api/generations/service.py"
MEDIA_DISPATCH = ROOT / "apps/api/src/lumi_api/media_dispatch.py"
PRODUCER_INTEGRATION = ROOT / "apps/api/tests/integration/test_generation_control_plane_postgres.py"
JOB_DISPATCH_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py"
WORKER_APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
WORKER_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py"
RUNTIME_MANIFEST = ROOT / "production/runtime-images/manifest-v1.json"
IMAGE_WORKFLOW = ROOT / ".github/workflows/image-generation.yml"
FINAL_WORKFLOW = ROOT / ".github/workflows/final-acceptance-gate.yml"
SELF_PATH = "scripts/validate_image_generation_producer_contract.py"


class ContractError(RuntimeError):
    pass


def _read(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"missing source: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _require(text: str, scope: str, *needles: str) -> None:
    for needle in needles:
        if needle not in text:
            raise ContractError(f"{scope}: missing {needle}")


def _forbid(text: str, scope: str, *needles: str) -> None:
    for needle in needles:
        if needle in text:
            raise ContractError(f"{scope}: forbidden {needle}")


def _require_order(text: str, scope: str, *needles: str) -> None:
    positions: list[int] = []
    cursor = -1
    for needle in needles:
        index = text.find(needle, cursor + 1)
        if index < 0:
            raise ContractError(f"{scope}: missing ordered marker {needle}")
        positions.append(index)
        cursor = index
    if positions != sorted(positions):
        raise ContractError(f"{scope}: ordered markers out of order")


def validate_product_api_binding() -> None:
    product = _read(PRODUCT_APP)
    router = _read(API_ROUTER)
    gateway = _read(GENERATION_GATEWAY)

    _require(
        product,
        "product_app",
        "from lumi_api.generations.gateway import GenerationRuntimeGateway",
        "base_gateway = cast(ApiV1Gateway, app.state.api_v1_gateway)",
        "app.state.api_v1_gateway = GenerationRuntimeGateway(base_gateway, session_factory)",
    )
    _require(
        router,
        "api/v1/router.py",
        '@router.post(\n    "/generations"',
        'operation_id="createGeneration"',
        "idempotency_key: IdempotencyDep",
        "resource = await gateway.create_generation(context, payload, idempotency_key)",
    )
    _require(
        gateway,
        "generations/gateway.py",
        'self._require(context, "project.write")',
        "async with self._session_factory() as session, session.begin():",
        'if payload.capability == "image.generate":',
        "await ImageGenerationControlPlane(session).create(",
        "organization_id=context.organization_id",
        "trace_id=context.trace_id",
        'raise GenerationInvalid("GENERATION_CAPABILITY_UNSUPPORTED")',
    )


def validate_canonical_producer_transaction() -> None:
    service = _read(GENERATION_SERVICE)
    dispatch = _read(MEDIA_DISPATCH)

    _require(
        service,
        "generations/service.py",
        'class ImageGenerationControlPlane:',
        '_OPERATION_TYPE = "api.v1.generation.create"',
        '_IMAGE_CAPABILITY = "image.generate"',
        "canonical_request_hash",
        "pg_advisory_xact_lock",
        "IdempotencyOperation(",
        "Generation(",
        "IMAGE_TRANSFORM_JOB_KIND",
        "IMAGE_TASK_INPUT_SCHEMA_VERSION",
        '"image_generation_spec": canonical_spec',
        "task.type != IMAGE_TRANSFORM_JOB_KIND",
        "type=IMAGE_TRANSFORM_JOB_KIND",
        "stage_image_transform_dispatch(",
        'provider=_PROVIDER_PENDING',
        'model=_MODEL_PENDING',
        'status="pending"',
        'operation.status = "succeeded"',
        'operation.result_ref = f"generation:{generation.id}"',
        "operation.response_status = 202",
    )
    _require_order(
        service,
        "generations/service.py",
        "task.input_json = canonical_task_input",
        "self.session.add(generation)",
        "stage_image_transform_dispatch(",
        'operation.status = "succeeded"',
    )
    _forbid(
        service,
        "generations/service.py DB-only producer boundary",
        "import httpx",
        "import requests",
        "Celery(",
        ".delay(",
        "send_task(",
    )

    _require(
        dispatch,
        "media_dispatch.py",
        "def build_image_transform_dispatch(",
        "def stage_image_transform_dispatch(",
        'expected_task_input_fields = {"schema_version", "job_kind", "image_generation_spec"}',
        'task_input.get("job_kind") != IMAGE_TRANSFORM_JOB_KIND',
        "task_spec.semantic_hash != generation_spec.semantic_hash",
        "MEDIA_DISPATCH_SPEC_ORGANIZATION_MISMATCH",
        "MEDIA_DISPATCH_SPEC_PROJECT_MISMATCH",
        "MEDIA_DISPATCH_SPEC_TASK_MISMATCH",
        "MEDIA_DISPATCH_SPEC_OPERATION_MISMATCH",
        "task_name=IMAGE_TRANSFORM_TASK_NAME",
        "queue=IMAGE_TRANSFORM_QUEUE",
        'namespace="image-transform"',
        "event_name=MEDIA_DISPATCH_EVENT_NAME",
        'aggregate_type="task"',
        "payload_json=dispatch.as_outbox_payload()",
    )


def validate_dispatcher_to_worker_binding() -> None:
    dispatcher = _read(JOB_DISPATCH_RUNTIME)
    app = _read(WORKER_APP)
    worker = _read(WORKER_RUNTIME)

    _require(
        dispatcher,
        "worker media canonical dispatcher",
        "IMAGE_TRANSFORM_TASK_NAME: (IMAGE_TRANSFORM_QUEUE, IMAGE_TRANSFORM_ROUTING_KEY)",
        "class MediaJobOutboxDispatcher",
        "JobDispatch.from_outbox_payload(self.payload)",
        "FOR UPDATE SKIP LOCKED",
        "SET publish_attempts = publish_attempts + 1",
        "celery_app.send_task(",
        "queue=dispatch.queue",
        "routing_key=routing_key",
        "SET published_at = now()",
    )
    _require_order(
        dispatcher,
        "worker media canonical dispatcher",
        "SET publish_attempts = publish_attempts + 1",
        "self.publisher.publish",
        "SET published_at = now()",
    )

    image_start = app.find('name="lumi.jobs.image.transform"')
    video_start = app.find('name="lumi.jobs.video.render"', image_start)
    if image_start < 0 or video_start <= image_start:
        raise ContractError("worker app: canonical image task block boundary missing")
    image_block = app[image_start:video_start]
    _require(
        image_block,
        "worker image.transform task",
        "def image_transform(",
        "JobMessage.from_mapping(message)",
        "_execute_image_generation_job(parsed)",
        "JobState.RETRYING",
        "JobState.FAILED",
    )
    _forbid(image_block, "worker image.transform task", '"status": "accepted"')
    _require(
        app,
        "worker image runtime binding",
        "HostedImageGenerationRuntime.from_env()",
        "TaskJobStore(_database_dsn())",
        "return await execute_job(",
        "handler=runtime.execute",
    )
    _require(
        worker,
        "worker image generation runtime",
        "class HostedImageGenerationRuntime",
        "SELECT type, input_json",
        '"image_generation_spec"',
        "IMAGE_GENERATION_TASK_OPERATION_MISMATCH",
        "HostedImageModelGatewayAdapter",
        "PostgresGenerationRepository",
    )


def validate_durable_acceptance_proof() -> None:
    integration = _read(PRODUCER_INTEGRATION)

    _require(
        integration,
        "generation_control_plane_postgres acceptance",
        "test_generation_control_plane_transaction_and_replay",
        'capability="image.generate"',
        'assert task.type == "image.transform"',
        'assert task.input_json["schema_version"] == 1',
        'assert task.input_json["job_kind"] == "image.transform"',
        'assert outbox_rows[0].payload_json["task_name"] == "lumi.jobs.image.transform"',
        'assert outbox_rows[0].payload_json["queue"] == "lumi.media.image"',
        'assert outbox_rows[0].payload_json["kwargs"] == {}',
        "assert len(outbox_rows) == 1",
        "assert len(idempotency_rows) == 1",
        "assert replay.id == first.id",
        "GENERATION_OPERATION_ALREADY_EXISTS",
    )


def validate_runtime_provenance() -> None:
    try:
        manifest = json.loads(_read(RUNTIME_MANIFEST))
    except json.JSONDecodeError as exc:
        raise ContractError("runtime image manifest is invalid JSON") from exc
    runtimes = manifest.get("runtimes")
    if not isinstance(runtimes, dict):
        raise ContractError("runtime image manifest: runtimes object missing")
    api = runtimes.get("api")
    worker = runtimes.get("worker-media")
    if not isinstance(api, dict) or not isinstance(worker, dict):
        raise ContractError("runtime image manifest: api/worker-media provenance missing")
    api_sources = set(api.get("source_paths") or [])
    worker_sources = set(worker.get("source_paths") or [])
    required_api = {
        "apps/api/src/lumi_api/product_app.py",
        "apps/api/src/lumi_api/generations/gateway.py",
        "apps/api/src/lumi_api/generations/service.py",
        "apps/api/src/lumi_api/media_dispatch.py",
    }
    required_worker = {
        "services/image-generation",
        "apps/worker-media/src/lumi_worker_media/app.py",
        "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
        "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py",
    }
    missing_api = required_api - api_sources
    missing_worker = required_worker - worker_sources
    if missing_api:
        raise ContractError(f"runtime image manifest: api producer provenance missing {sorted(missing_api)}")
    if missing_worker:
        raise ContractError(
            f"runtime image manifest: worker producer-consumer provenance missing {sorted(missing_worker)}"
        )


def validate_workflow_gates() -> None:
    image_workflow = _read(IMAGE_WORKFLOW)
    final_workflow = _read(FINAL_WORKFLOW)

    _require(
        image_workflow,
        "Image Generation workflow producer gate",
        f'- "{SELF_PATH}"',
        f"python {SELF_PATH}",
        SELF_PATH,
        "apps/api/src/lumi_api/product_app.py",
        "apps/api/src/lumi_api/api/v1/router.py",
        "apps/api/src/lumi_api/generations/gateway.py",
        "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
        "production/runtime-images/manifest-v1.json",
    )
    if image_workflow.count(SELF_PATH) < 3:
        raise ContractError(
            "Image Generation workflow producer gate: contract must be path-filtered, compiled, and executed"
        )

    _require(
        final_workflow,
        "Final Acceptance image producer gate",
        f"python3 {SELF_PATH}",
        SELF_PATH,
    )
    if final_workflow.count(SELF_PATH) < 2:
        raise ContractError(
            "Final Acceptance image producer gate: contract must be both executed and syntax-gated"
        )


def main() -> int:
    validate_product_api_binding()
    validate_canonical_producer_transaction()
    validate_dispatcher_to_worker_binding()
    validate_durable_acceptance_proof()
    validate_runtime_provenance()
    validate_workflow_gates()
    print(
        "NODE-73 canonical image producer source contract: PASS "
        "(product API -> canonical Generation/Task/spec -> outbox -> dispatcher -> Worker)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"canonical image producer source contract failed: {exc}") from exc

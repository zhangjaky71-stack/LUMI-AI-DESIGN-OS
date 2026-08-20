#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCT_APP = ROOT / "apps/api/src/lumi_api/product_app.py"
API_ROUTER = ROOT / "apps/api/src/lumi_api/api/v1/router.py"
GENERATION_GATEWAY = ROOT / "apps/api/src/lumi_api/generations/gateway.py"
GENERATION_SERVICE = ROOT / "apps/api/src/lumi_api/generations/service.py"
MEDIA_DISPATCH = ROOT / "apps/api/src/lumi_api/media_dispatch.py"
PRODUCER_INTEGRATION = ROOT / "apps/api/tests/integration/test_generation_control_plane_postgres.py"
WORKER_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py"


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
        "await ImageGenerationControlPlane(session).create(",
        "organization_id=context.organization_id",
        "trace_id=context.trace_id",
    )


def validate_canonical_producer_transaction() -> None:
    service = _read(GENERATION_SERVICE)
    dispatch = _read(MEDIA_DISPATCH)

    _require(
        service,
        "generations/service.py",
        "IMAGE_TRANSFORM_JOB_KIND",
        "IMAGE_TASK_INPUT_SCHEMA_VERSION",
        '"image_generation_spec": canonical_spec',
        "task.type != IMAGE_TRANSFORM_JOB_KIND",
        "type=IMAGE_TRANSFORM_JOB_KIND",
        "stage_image_transform_dispatch(",
        'operation.status = "succeeded"',
        'operation.result_ref = f"generation:{generation.id}"',
    )
    _require_order(
        service,
        "generations/service.py",
        "task.input_json = canonical_task_input",
        "self.session.add(generation)",
        "stage_image_transform_dispatch(",
        'operation.status = "succeeded"',
    )

    _require(
        dispatch,
        "media_dispatch.py",
        'expected_task_input_fields = {"schema_version", "job_kind", "image_generation_spec"}',
        'task_input.get("job_kind") != IMAGE_TRANSFORM_JOB_KIND',
        "task_name=IMAGE_TRANSFORM_TASK_NAME",
        "queue=IMAGE_TRANSFORM_QUEUE",
        "event_name=MEDIA_DISPATCH_EVENT_NAME",
        'aggregate_type="task"',
        "payload_json=dispatch.as_outbox_payload()",
    )


def validate_durable_acceptance_proof() -> None:
    integration = _read(PRODUCER_INTEGRATION)
    worker = _read(WORKER_RUNTIME)

    _require(
        integration,
        "generation_control_plane_postgres acceptance",
        'assert task.type == "image.transform"',
        'assert task.input_json["schema_version"] == 1',
        'assert task.input_json["job_kind"] == "image.transform"',
        'assert outbox_rows[0].payload_json["task_name"] == "lumi.jobs.image.transform"',
        'assert outbox_rows[0].payload_json["queue"] == "lumi.media.image"',
        "assert len(outbox_rows) == 1",
        "assert len(idempotency_rows) == 1",
    )
    _require(
        worker,
        "worker image generation runtime",
        "SELECT type, input_json",
        '"image_generation_spec"',
        "IMAGE_GENERATION_TASK_OPERATION_MISMATCH",
    )


def main() -> int:
    validate_product_api_binding()
    validate_canonical_producer_transaction()
    validate_durable_acceptance_proof()
    print("NODE-73 canonical image producer source contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"canonical image producer source contract failed: {exc}") from exc

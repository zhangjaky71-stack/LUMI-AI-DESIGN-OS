from __future__ import annotations

import asyncio
from dataclasses import replace

from lumi_image_edit import (
    EditFinding,
    EditIntent,
    EditValidationReport,
    GatewayEditResult,
    ImageEditPipelineError,
    MaskSpec,
    PixelRect,
    ProtectedRegion,
)
from node47_support import (
    SHA,
    Auth,
    Canvas,
    Compositor,
    Gateway,
    Validator,
    base,
    pipe,
    source,
)


def _mask() -> MaskSpec:
    return MaskSpec(
        "m",
        "1",
        "USER_BRUSH",
        "asset",
        "7",
        SHA,
        1000,
        1000,
        PixelRect(0, 0, 300, 1000),
        "d" * 64,
        "bucket/mask.png",
    )


def test_pixel_success_appends_v4_and_updates_canvas_only_after_pass() -> None:
    pipeline, _ = pipe()
    pipeline.canvas = Canvas()
    spec = base(
        operation_id="pixel",
        mask=_mask(),
        design_document_id="doc",
        design_document_version=3,
        intent=EditIntent(
            "BACKGROUND_REPLACE",
            "black",
            ("image-node",),
        ),
    )
    queued = asyncio.run(pipeline.submit(spec))
    assert queued.status == "QUEUED"
    done = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=queued.edit_id)
    )
    assert done.status == "COMPLETED"
    assert done.source_artifact_version_id == "v3"
    assert done.result_artifact_version_id == "v4"
    assert pipeline.canvas.calls == 1


def test_reject_never_updates_canvas_and_source_version_remains() -> None:
    pipeline, _ = pipe(validator=Validator("REJECT"))
    pipeline.canvas = Canvas()
    spec = base(
        operation_id="reject",
        mask=_mask(),
        design_document_id="doc",
        design_document_version=3,
        intent=EditIntent(
            "BACKGROUND_REPLACE",
            "black",
            ("image-node",),
        ),
    )
    queued = asyncio.run(pipeline.submit(spec))
    done = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=queued.edit_id)
    )
    assert done.status == "REJECTED"
    assert done.source_artifact_version_id == "v3"
    assert pipeline.canvas.calls == 0


def test_pending_poll_uncertainty_remains_pending() -> None:
    class Pending(Gateway):
        async def poll(self, request, pending):
            del request, pending
            raise TimeoutError

    gateway = Pending(GatewayEditResult("PENDING", "mock", "edit", "remote"))
    pipeline, _ = pipe(gateway=gateway)
    queued = asyncio.run(
        pipeline.submit(base(operation_id="pending", mask=_mask()))
    )
    current = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=queued.edit_id)
    )
    assert current.status == "PROVIDER_PENDING"
    current = asyncio.run(
        pipeline.resume_pending(
            organization_id="org",
            edit_id_value=queued.edit_id,
        )
    )
    assert current.status == "PROVIDER_PENDING"
    assert current.error_code is not None
    assert "POLL_DEFERRED" in current.error_code


def test_operation_idempotency_replays_and_semantic_conflict_fails() -> None:
    pipeline, _ = pipe()
    spec = base(operation_id="same", mask=_mask())
    first = asyncio.run(pipeline.submit(spec))
    second = asyncio.run(pipeline.submit(spec))
    assert first == second
    changed = replace(
        spec,
        intent=EditIntent("BACKGROUND_REPLACE", "white"),
    )
    try:
        asyncio.run(pipeline.submit(changed))
    except ImageEditPipelineError as exc:
        assert "SEMANTIC_CONFLICT" in str(exc)
    else:
        raise AssertionError("semantic conflict accepted")


def test_source_version_reauthorized_before_worker() -> None:
    pipeline, _ = pipe()
    queued = asyncio.run(
        pipeline.submit(base(operation_id="reauth", mask=_mask()))
    )
    pipeline.authorization = Auth(replace(source(), asset_version="8"))
    try:
        asyncio.run(
            pipeline.execute(
                organization_id="org",
                edit_id_value=queued.edit_id,
            )
        )
    except ImageEditPipelineError:
        pass
    else:
        raise AssertionError("changed source accepted")


def test_compositor_fallback_revalidates_protected_content() -> None:
    region = ProtectedRegion(
        "logo",
        "LOGO",
        PixelRect(600, 100, 100, 100),
        "HARD",
        SHA,
    )

    class RepairValidator:
        def __init__(self) -> None:
            self.calls = 0

        async def validate(self, **kwargs) -> EditValidationReport:
            del kwargs
            self.calls += 1
            status = "FAIL" if self.calls == 1 else "PASS"
            return EditValidationReport(
                (
                    EditFinding(
                        "protected-region",
                        status,
                        "HARD",
                        "PROTECTED",
                    ),
                )
            )

    validator = RepairValidator()
    compositor = Compositor()
    pipeline, _ = pipe(validator=validator, compositor=compositor)
    queued = asyncio.run(
        pipeline.submit(
            base(
                operation_id="composite",
                mask=_mask(),
                protected_regions=(region,),
            )
        )
    )
    done = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=queued.edit_id)
    )
    assert done.status == "COMPLETED"
    assert compositor.calls == 1
    assert validator.calls == 2

from __future__ import annotations

import asyncio

from lumi_image_edit import (
    EditIntent,
    MaskSpec,
    PixelRect,
    ProtectedRegion,
    normalized_rect_to_pixels,
    plan_edit,
    validate_mask,
)
from node47_support import SHA, Gateway, Structural, base, pipe, source


def _mask(
    *,
    source_kind: str = "USER_BRUSH",
    rect: PixelRect | None = None,
    preview_required: bool = False,
) -> MaskSpec:
    return MaskSpec(
        "m",
        "1",
        source_kind,
        "asset",
        "7",
        SHA,
        1000,
        1000,
        rect or PixelRect(0, 0, 300, 1000),
        "d" * 64,
        "bucket/mask.png",
        preview_required,
        None,
    )


def test_structural_first_never_calls_provider() -> None:
    pipeline, _ = pipe()
    pipeline.structural = Structural()
    pipeline.gateway = Gateway()
    spec = base(
        operation_id="struct",
        intent=EditIntent(
            "RESIZE_TEXT",
            "resize title",
            ("title",),
            {"width": 500, "height": 120},
        ),
        design_document_id="doc",
        design_document_version=3,
    )
    job = asyncio.run(pipeline.submit(spec))
    assert job.status == "COMPLETED"
    assert pipeline.gateway.calls == 0
    assert pipeline.structural.calls == 1
    assert job.result_design_document_version_id == "design-v4"


def test_normalized_mask_conversion_and_hard_overlap_rejected() -> None:
    rect = normalized_rect_to_pixels(
        x=0.1,
        y=0.2,
        width=0.3,
        height=0.4,
        source_width=1000,
        source_height=500,
    )
    assert rect == PixelRect(100, 100, 300, 200)
    mask = _mask(rect=PixelRect(0, 0, 500, 1000))
    region = ProtectedRegion(
        "product",
        "PRODUCT",
        PixelRect(400, 100, 200, 200),
        "HARD",
        SHA,
    )
    try:
        validate_mask(mask, source(), (region,))
    except ValueError as exc:
        assert "OVERLAPS_HARD" in str(exc)
    else:
        raise AssertionError("overlap accepted")


def test_high_impact_agent_mask_waits_for_preview_approval() -> None:
    mask = _mask(
        source_kind="AGENT_PROPOSED",
        rect=PixelRect(0, 0, 300, 300),
        preview_required=True,
    )
    pipeline, _ = pipe()
    job = asyncio.run(
        pipeline.submit(base(operation_id="preview", mask=mask))
    )
    assert job.status == "AWAITING_MASK_APPROVAL"
    assert pipeline.gateway.calls == 0


def test_hard_local_edit_requires_mask_and_reference_capabilities() -> None:
    mask = _mask()
    region = ProtectedRegion(
        "product",
        "PRODUCT",
        PixelRect(400, 100, 200, 200),
        "HARD",
        SHA,
        identity_id="id",
    )
    spec = base(
        operation_id="caps",
        mask=mask,
        protected_regions=(region,),
        identity_requirement_ids=("id",),
    )
    plan = plan_edit(spec)
    assert plan.required_capabilities == (
        "image.mask_edit",
        "image.reference_consistency",
    )


def test_mask_approval_is_lifecycle_not_semantic_change() -> None:
    mask = _mask(
        source_kind="AGENT_PROPOSED",
        rect=PixelRect(0, 0, 300, 300),
        preview_required=True,
    )
    pipeline, _ = pipe()
    job = asyncio.run(
        pipeline.submit(base(operation_id="approve", mask=mask))
    )
    assert job.status == "AWAITING_MASK_APPROVAL"
    ready = asyncio.run(
        pipeline.approve_mask(
            organization_id="org",
            edit_id_value=job.edit_id,
            approved_by="user-1",
        )
    )
    assert ready.status == "QUEUED"
    done = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=job.edit_id)
    )
    assert done.status == "COMPLETED"


def test_broad_change_confirmation_is_explicit_lifecycle_gate() -> None:
    region = ProtectedRegion(
        "product",
        "PRODUCT",
        PixelRect(400, 100, 200, 200),
        "HARD",
        SHA,
    )
    pipeline, _ = pipe()
    spec = base(
        operation_id="confirm",
        intent=EditIntent(
            "RELIGHT",
            "relight all",
            allow_broad_change=True,
        ),
        protected_regions=(region,),
    )
    job = asyncio.run(pipeline.submit(spec))
    assert job.status == "AWAITING_CONFIRMATION"
    assert pipeline.gateway.calls == 0
    ready = asyncio.run(
        pipeline.confirm_broad_change(
            organization_id="org",
            edit_id_value=job.edit_id,
            confirmed_by="user-1",
        )
    )
    assert ready.status == "QUEUED"

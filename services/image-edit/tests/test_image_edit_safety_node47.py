from __future__ import annotations

import asyncio
from decimal import Decimal

from lumi_image_edit import (
    CompositePostflight,
    EditConstraint,
    EditIntent,
    GatewayEditResult,
    MaskSpec,
    PixelRect,
    ValidatedImage,
)
from node47_support import Canvas, Gateway, SHA, Validator, base, pipe, source


def test_composite_postflight_fails_closed_for_constraint_and_brand_outage() -> None:
    spec = base(
        operation_id="postflight-outage",
        constraints=(
            EditConstraint("c1", "LOCK_POSITION", "HARD", "1" * 64),
        ),
        brand_rule_set_version="brand-rules-v3",
    )
    image = ValidatedImage(
        "generated",
        "edit.png",
        "c" * 64,
        "image/png",
        1000,
        1000,
        100,
    )
    report = asyncio.run(
        CompositePostflight().validate(
            spec=spec,
            image=image,
            source=source(),
        )
    )
    assert report.decision == "REJECT"
    reasons = {finding.reason_code for finding in report.findings}
    assert "IMAGE_EDIT_CONSTRAINT_VALIDATOR_UNAVAILABLE" in reasons
    assert "IMAGE_EDIT_BRAND_RULES_ENGINE_UNAVAILABLE" in reasons


def test_provider_safety_block_cannot_be_repaired_or_update_canvas() -> None:
    mask = MaskSpec(
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
    result = GatewayEditResult(
        status="SUCCEEDED",
        provider="mock",
        model="edit-v1",
        provider_request_id="req-safety",
        output_ref="provider://output",
        output_mime_type="image/png",
        cost_usd=Decimal("0.2"),
        cost_confidence="exact",
        pricing_snapshot_id="price",
        routing_reason_codes=("route",),
        safety_metadata={},
        finish_reason="content_filter",
    )
    pipeline, _ = pipe(
        gateway=Gateway(result),
        validator=Validator("PASS"),
    )
    pipeline.canvas = Canvas()
    queued = asyncio.run(
        pipeline.submit(
            base(
                operation_id="safety",
                mask=mask,
                design_document_id="doc",
                design_document_version=3,
                intent=EditIntent(
                    "BACKGROUND_REPLACE",
                    "black",
                    ("image-node",),
                ),
            )
        )
    )
    done = asyncio.run(
        pipeline.execute(organization_id="org", edit_id_value=queued.edit_id)
    )
    assert done.status == "REJECTED"
    assert done.validation_decision == "REJECT"
    assert pipeline.canvas.calls == 0
